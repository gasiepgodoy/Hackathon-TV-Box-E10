"""Enviador: consome a fila pendente e entrega pelo backhaul.

O transporte e plugavel de proposito. Hoje ele apenas registra em log ou publica
em MQTT; para o backhaul real (Wi-Fi/4G) implemente `TransporteHTTP`, e para a
rota de emergencia por LoRa um `TransporteSerial` — nenhuma outra parte do
sistema muda.

Ordem de saida: eventos primeiro (raros e urgentes), agregados depois. Dados
brutos so quando houver banda sobrando.

O empacotamento binario abaixo dimensiona as mensagens para a rota de
emergencia por LoRa, onde cada byte conta. Num backhaul IP ele e desnecessario,
mas inofensivo.
"""
from __future__ import annotations

import argparse
import logging
import struct
import subprocess
import sqlite3
import sys
import time

from .config import Config
from .db import conectar, inicializar

log = logging.getLogger("hub.enviador")

TIPO_EVENTO = 1
TIPO_AGREGADO = 2

# Limite conservador: no AU915, a taxa mais baixa (DR0) admite 51 bytes de
# payload. Manter as mensagens abaixo disso garante entrega em qualquer SF.
LIMITE_PAYLOAD = 51


def _di(valor: float | None) -> int:
    """Graus -> decigraus em int16 (0.1 C de resolucao). None vira sentinela."""
    if valor is None:
        return -32768
    return max(-32767, min(32767, int(round(valor * 10))))


def _u8(valor: float | None) -> int:
    if valor is None:
        return 255
    return max(0, min(254, int(round(valor))))


def empacotar_agregado(r: sqlite3.Row) -> bytes:
    """14 bytes por agregado — cabem 3 sensores numa unica mensagem LoRa (51 B)."""
    return struct.pack(
        "<BBIhhhBB",
        TIPO_AGREGADO,
        r["sensor_id"] & 0xFF,
        r["inicio"] // 60,          # minutos desde epoch cabem em uint32 ate 10136
        _di(r["temp_min"]),
        _di(r["temp_max"]),
        _di(r["temp_media"]),
        _u8(r["umid_media"]),
        _u8(r["bateria"]),
    )


def empacotar_evento(r: sqlite3.Row, tipos: dict[str, int]) -> bytes:
    """9 bytes por evento."""
    return struct.pack(
        "<BBIhB",
        TIPO_EVENTO,
        (r["sensor_id"] or 0) & 0xFF,
        r["ts"] // 60,
        _di(r["valor"]),
        tipos.get(r["tipo"], 0),
    )


class Transporte:
    """Interface do enlace de longa distancia."""

    def enviar(self, payload: bytes) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class TransporteLog(Transporte):
    """Padrao enquanto o LoRa nao existe: registra e considera entregue."""

    def enviar(self, payload: bytes) -> bool:
        log.info("LoRa (simulado) %d bytes: %s", len(payload), payload.hex(" "))
        return True


class TransporteMQTT(Transporte):
    """Publica em MQTT — util para visualizar a saida durante a demonstracao."""

    def __init__(self, host: str, port: str, topico: str):
        self.host, self.port, self.topico = host, port, topico

    def enviar(self, payload: bytes) -> bool:
        r = subprocess.run(
            ["mosquitto_pub", "-h", self.host, "-p", self.port,
             "-t", self.topico, "-m", payload.hex()],
            capture_output=True,
        )
        if r.returncode != 0:
            log.warning("falha ao publicar: %s", r.stderr.decode().strip())
            return False
        return True


class TransporteIndisponivel(Transporte):
    """Simula enlace fora do ar — para demonstrar o acumulo na fila."""

    def enviar(self, payload: bytes) -> bool:
        log.warning("enlace indisponivel; %d bytes permanecem na fila", len(payload))
        return False


def tipos_evento(con: sqlite3.Connection) -> dict[str, int]:
    """Mapeia tipo textual -> codigo numerico, para caber em 1 byte no radio."""
    from .eventos import PRIORIDADES

    return {t: i + 1 for i, t in enumerate(sorted(PRIORIDADES))}


def enviar_pendentes(con: sqlite3.Connection, transporte: Transporte,
                     max_mensagens: int = 10) -> dict[str, int]:
    """Envia eventos e depois agregados. So marca `enviado` se o transporte confirmar."""
    codigos = tipos_evento(con)
    enviados = {"eventos": 0, "agregados": 0, "bytes": 0}
    restantes = max_mensagens

    eventos = con.execute(
        "SELECT * FROM eventos WHERE enviado = 0 ORDER BY prioridade DESC, ts LIMIT ?",
        (restantes,),
    ).fetchall()
    for r in eventos:
        if transporte.enviar(empacotar_evento(r, codigos)):
            con.execute(
                "UPDATE eventos SET enviado = 1, enviado_em = ? WHERE id = ?",
                (int(time.time()), r["id"]),
            )
            enviados["eventos"] += 1
            enviados["bytes"] += 9
            restantes -= 1
        else:
            return enviados            # enlace caiu: preserva a fila para depois

    if restantes <= 0:
        return enviados

    agregados = con.execute(
        "SELECT * FROM agregados WHERE enviado = 0 ORDER BY inicio LIMIT ?",
        (restantes,),
    ).fetchall()

    # Agrupa em mensagens que respeitem o limite de payload do LoRa.
    lote: list[sqlite3.Row] = []
    corpo = b""
    for r in agregados:
        p = empacotar_agregado(r)
        if len(corpo) + len(p) > LIMITE_PAYLOAD and lote:
            if not transporte.enviar(corpo):
                return enviados
            _marcar(con, lote)
            enviados["agregados"] += len(lote)
            enviados["bytes"] += len(corpo)
            lote, corpo = [], b""
        lote.append(r)
        corpo += p
    if lote:
        if transporte.enviar(corpo):
            _marcar(con, lote)
            enviados["agregados"] += len(lote)
            enviados["bytes"] += len(corpo)

    return enviados


def _marcar(con: sqlite3.Connection, linhas: list[sqlite3.Row]) -> None:
    agora = int(time.time())
    con.executemany(
        "UPDATE agregados SET enviado = 1, enviado_em = ? WHERE id = ?",
        [(agora, r["id"]) for r in linhas],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Envia a fila pendente pelo enlace LoRa")
    ap.add_argument("--transporte", choices=("log", "mqtt", "offline"), default="log",
                    help="offline simula o enlace fora do ar")
    ap.add_argument("--max", type=int, default=10, help="maximo de mensagens por execucao")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    cfg = Config()
    con = conectar(cfg.txt("banco", "caminho"))
    inicializar(con)

    if args.transporte == "mqtt":
        t: Transporte = TransporteMQTT(cfg.txt("mqtt", "host"), cfg.txt("mqtt", "port"),
                                       cfg.txt("mqtt", "topico_saida"))
    elif args.transporte == "offline":
        t = TransporteIndisponivel()
    else:
        t = TransporteLog()

    res = enviar_pendentes(con, t, args.max)
    print(f"eventos={res['eventos']} agregados={res['agregados']} bytes={res['bytes']}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
