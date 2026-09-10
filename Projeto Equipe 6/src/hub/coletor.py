"""Coletor: assina o MQTT e grava as leituras em lote.

Escuta as DUAS origens do hub e as normaliza para o mesmo formato de leitura:

  zigbee2mqtt/<nome>                          sensores Zigbee (Tuya TS0201)
  application/<id>/device/<devEUI>/event/up   nos LoRaWAN (via ChirpStack)

Usa o `mosquitto_sub` como transporte para nao exigir nenhuma dependencia
Python na TV box (o pacote mosquitto-clients ja e necessario de qualquer forma).
O systemd reinicia o servico se o processo cair, cobrindo reconexao.
"""
from __future__ import annotations

import base64
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


def _num(d: dict, *nomes):
    """Primeiro valor numerico presente entre varios nomes possiveis de campo.

    Firmwares diferentes nomeiam as grandezas de formas diferentes ('temperature',
    'temp', 't'), e nao controlamos o codec do ChirpStack.
    """
    for n in nomes:
        v = d.get(n)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _grandezas(d: dict) -> dict:
    return {
        "temperatura": _num(d, "temperature", "temperatura", "temp", "t"),
        "umidade":     _num(d, "humidity", "umidade", "hum", "h"),
        "pressao":     _num(d, "pressure", "pressao", "press", "p"),
        "bateria":     _num(d, "battery", "bateria", "bat"),
    }


def _do_chirpstack(topico: str, payload: str):
    """Uplink LoRaWAN publicado pelo ChirpStack.

    Topico: application/{id}/device/{devEUI}/event/up
    O payload traz os dados em 'object' (se houver codec configurado) ou em
    'data', codificado em base64.
    """
    try:
        m = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None, "payload do ChirpStack nao e JSON"
    if not isinstance(m, dict):
        return None, "payload do ChirpStack nao e um objeto"

    info = m.get("deviceInfo") or {}
    nome = info.get("deviceName") or info.get("devEui") or topico.split("/")[-3]

    corpo = m.get("object")
    if not isinstance(corpo, dict):
        # Sem codec no ChirpStack: tentamos decodificar o base64 como JSON, que
        # e o formato que o firmware do no envia hoje.
        bruto = m.get("data")
        if not bruto:
            return None, "uplink sem 'object' nem 'data'"
        try:
            corpo = json.loads(base64.b64decode(bruto).decode("utf-8"))
        except Exception:
            return None, ("payload nao decodifica como JSON; configure um codec "
                          f"no Device Profile do ChirpStack (data={bruto!r})")
        if not isinstance(corpo, dict):
            return None, "payload decodificado nao e um objeto JSON"

    g = _grandezas(corpo)
    if g["temperatura"] is None and g["umidade"] is None and g["pressao"] is None:
        return None, f"sem grandezas reconhecidas; campos: {sorted(corpo)}"

    # No LoRa nao ha LQI; usamos o RSSI do gateway que melhor recebeu.
    rssi = None
    rx = m.get("rxInfo") or []
    if isinstance(rx, list) and rx:
        valores = [r.get("rssi") for r in rx if isinstance(r.get("rssi"), (int, float))]
        if valores:
            rssi = max(valores)

    return {"ieee": nome, "ts": int(time.time()), "linkquality": rssi,
            "transporte": "lora", **g}, "ok"


def _do_zigbee(topico: str, payload: str):
    """Estado de dispositivo publicado pelo Zigbee2MQTT."""
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

    g = _grandezas(d)
    if g["temperatura"] is None and g["umidade"] is None:
        return None, f"sem temperature/humidity; campos presentes: {sorted(d)}"

    return {"ieee": nome, "ts": int(time.time()),
            "linkquality": _num(d, "linkquality"),
            "transporte": "zigbee", **g}, "ok"


def diagnosticar(topico: str, payload: str):
    """Converte uma mensagem MQTT numa leitura, ou explica por que a descartou.

    Aceita as duas origens do hub: Zigbee2MQTT e ChirpStack. O motivo devolvido
    e usado por `hub.cli espiar` para depurar leituras que nao chegam ao banco.
    """
    if topico.startswith("application/"):
        if not topico.endswith("/event/up"):
            return None, "evento do ChirpStack que nao e uplink"
        return _do_chirpstack(topico, payload)
    return _do_zigbee(topico, payload)


def extrair(topico: str, payload: str):
    """Devolve o dict da leitura, ou None se a mensagem nao interessa."""
    leitura, _motivo = diagnosticar(topico, payload)
    return leitura


def executar(cfg: Config) -> int:
    con = conectar(cfg.txt("banco", "caminho"))
    inicializar(con)

    lote_max = cfg.num("coletor", "lote_max")
    intervalo = cfg.num("coletor", "intervalo_flush_s")

    # Um -t por origem; o mosquitto_sub aceita varios.
    topicos = [t for t in (cfg.txt("mqtt", "topico"),
                           cfg.txt("mqtt", "topico_lora")) if t]
    cmd = ["mosquitto_sub", "-h", cfg.txt("mqtt", "host"),
           "-p", cfg.txt("mqtt", "port"), "-F", "%j"]
    for t in topicos:
        cmd += ["-t", t]
    log.info("assinando %s em %s:%s", " e ".join(topicos),
             cfg.txt("mqtt", "host"), cfg.txt("mqtt", "port"))

    buffer: list[dict] = []
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
                        log.debug("%s (%s) -> %s", leitura["ieee"],
                                  leitura.get("transporte"),
                                  {k: v for k, v in leitura.items()
                                   if k not in ("ieee", "ts") and v is not None})
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
