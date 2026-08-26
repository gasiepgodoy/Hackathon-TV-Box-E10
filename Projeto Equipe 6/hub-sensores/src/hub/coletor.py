"""Coletor: assina o MQTT do Zigbee2MQTT e grava as leituras em lote.

Usa o `mosquitto_sub` como transporte para nao exigir nenhuma dependencia
Python na TV box (o pacote mosquitto-clients ja e necessario de qualquer forma).
O systemd reinicia o servico se o processo cair, cobrindo reconexao.
"""
from __future__ import annotations

import json
import logging
import queue
import signal
import subprocess
import sys
import threading
import time

from .config import Config
from .db import conectar, gravar_leituras, inicializar

log = logging.getLogger("hub.coletor")

# Campos publicados pelo Zigbee2MQTT que nos interessam.
CAMPOS = ("temperature", "humidity", "battery", "linkquality")


def parse_linha(linha: str):
    """Extrai (topico, payload) de uma linha do `mosquitto_sub -F %j`.

    Usamos o formato JSON em vez de "%t %p" porque o Zigbee2MQTT aceita
    espacos no nome do dispositivo: com "Sensor Temperatura", separar pelo
    primeiro espaco partia o topico ao meio e o payload virava lixo.
    """
    linha = linha.strip()
    if not linha:
        return None
    try:
        m = json.loads(linha)
        return m["topic"], m.get("payload", "")
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def diagnosticar(topico: str, payload: str):
    """Como `extrair`, mas devolve tambem o motivo de uma mensagem ser descartada.

    Usado por `hub.cli espiar` para depurar por que leituras reais nao chegam
    ao banco.
    """
    nome = topico.split("/", 1)[-1]
    if nome.startswith("bridge"):
        return None, "topico interno do Z2M (bridge)"
    if "/" in nome:
        return None, f"topico com nivel extra ('{nome}') — availability ou modo attribute"
    try:
        d = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None, "payload nao e JSON (Z2M em modo 'attribute'?)"
    if not isinstance(d, dict):
        return None, "payload JSON nao e um objeto"
    if d.get("temperature") is None and d.get("humidity") is None:
        return None, f"sem temperature/humidity; campos presentes: {sorted(d)}"
    return (
        nome,
        int(time.time()),
        d.get("temperature"),
        d.get("humidity"),
        d.get("battery"),
        d.get("linkquality"),
    ), "ok"


def extrair(topico: str, payload: str):
    """Converte uma mensagem do Z2M numa linha de leitura, ou None se irrelevante."""
    leitura, _motivo = diagnosticar(topico, payload)
    return leitura


def executar(cfg: Config) -> int:
    con = conectar(cfg.txt("banco", "caminho"))
    inicializar(con)

    lote_max = cfg.num("coletor", "lote_max")
    intervalo = cfg.num("coletor", "intervalo_flush_s")

    cmd = [
        "mosquitto_sub",
        "-h", cfg.txt("mqtt", "host"),
        "-p", cfg.txt("mqtt", "port"),
        "-t", cfg.txt("mqtt", "topico"),
        "-F", "%j",
    ]
    log.info("assinando %s em %s:%s", cfg.txt("mqtt", "topico"),
             cfg.txt("mqtt", "host"), cfg.txt("mqtt", "port"))

    buffer: list[tuple] = []
    ultimo_flush = time.time()
    encerrar = False

    def descarregar():
        nonlocal ultimo_flush
        if buffer:
            n = gravar_leituras(con, buffer)
            log.info("gravadas %d leituras", n)
            buffer.clear()
        ultimo_flush = time.time()

    def ao_sinal(_signo, _frame):
        nonlocal encerrar
        encerrar = True

    signal.signal(signal.SIGTERM, ao_sinal)
    signal.signal(signal.SIGINT, ao_sinal)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, bufsize=1)
    assert proc.stdout is not None

    # A leitura do MQTT vai para uma thread e chega por fila. Sem isso, o laco
    # principal ficaria bloqueado esperando mensagem: nao responderia ao SIGTERM
    # (perdendo o buffer ao desligar) nem faria o flush periodico com os
    # sensores quietos.
    fila: queue.Queue = queue.Queue()

    def bombear():
        try:
            for linha in proc.stdout:      # type: ignore[union-attr]
                fila.put(linha)
        finally:
            fila.put(None)                 # sentinela: transporte terminou

    threading.Thread(target=bombear, daemon=True).start()

    try:
        while not encerrar:
            try:
                linha = fila.get(timeout=1.0)
            except queue.Empty:
                linha = ""
            if linha is None:
                log.warning("mosquitto_sub encerrou; saindo para o systemd reiniciar")
                break
            if linha:
                msg = parse_linha(linha)
                if msg:
                    leitura = extrair(*msg)
                    if leitura:
                        buffer.append(leitura)
                        log.debug("%s -> %s", leitura[0], leitura[2:])
            if len(buffer) >= lote_max or (time.time() - ultimo_flush) >= intervalo:
                descarregar()
    finally:
        descarregar()                    # nao perde o que estava em memoria
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        con.close()
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    return executar(Config())


if __name__ == "__main__":
    sys.exit(main())
