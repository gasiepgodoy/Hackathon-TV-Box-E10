"""Deteccao de eventos — o processamento de borda do hub.

Roda localmente, sem depender do servidor. Eventos sao curtos e urgentes:
sobem pelo LoRa na frente dos agregados.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
import time

from .config import Config
from .db import conectar, inicializar

log = logging.getLogger("hub.eventos")

# tipo -> prioridade (maior sobe primeiro)
PRIORIDADES = {
    "geada": 5,
    "calor_extremo": 4,
    "sensor_mudo": 3,
    "umidade_baixa": 2,
    "umidade_alta": 2,
    "bateria_baixa": 1,
}


def _registrar(con, sensor_id, ts, tipo, valor, detalhe, repetir_apos_s) -> bool:
    """Insere o evento, a menos que um igual tenha sido registrado ha pouco.

    Sem essa guarda, um sensor oscilando no limiar geraria centenas de eventos
    e entupiria a fila estreita do LoRa.
    """
    recente = con.execute(
        "SELECT 1 FROM eventos WHERE sensor_id IS ? AND tipo = ? AND ts > ? LIMIT 1",
        (sensor_id, tipo, ts - repetir_apos_s),
    ).fetchone()
    if recente:
        return False
    con.execute(
        "INSERT INTO eventos (sensor_id, ts, tipo, valor, detalhe, prioridade)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (sensor_id, ts, tipo, valor, detalhe, PRIORIDADES.get(tipo, 1)),
    )
    log.info("evento %s sensor=%s valor=%s", tipo, sensor_id, valor)
    return True


def detectar(con: sqlite3.Connection, cfg: Config, agora: int | None = None) -> int:
    agora = agora if agora is not None else int(time.time())
    repetir = cfg.num("eventos", "repetir_apos_s")
    t_min = cfg.dec("eventos", "temp_min")
    t_max = cfg.dec("eventos", "temp_max")
    u_min = cfg.dec("eventos", "umid_min")
    u_max = cfg.dec("eventos", "umid_max")
    bat_min = cfg.num("eventos", "bateria_min")
    silencio = cfg.num("eventos", "silencio_s")

    novos = 0
    con.execute("BEGIN")
    try:
        # Ultima leitura de cada sensor cadastrado.
        ultimas = con.execute(
            """
            SELECT s.id AS sensor_id, s.ieee,
                   l.ts, l.temperatura, l.umidade, l.bateria
              FROM sensores s
              LEFT JOIN leituras l ON l.id = (
                    SELECT id FROM leituras WHERE sensor_id = s.id
                     ORDER BY ts DESC LIMIT 1)
            """
        ).fetchall()

        for r in ultimas:
            sid, ieee, ts = r["sensor_id"], r["ieee"], r["ts"]

            if ts is None or (agora - ts) > silencio:
                mudo_desde = "nunca reportou" if ts is None else f"{(agora - ts) // 60} min"
                novos += _registrar(con, sid, agora, "sensor_mudo", None,
                                    f"{ieee} sem dados ha {mudo_desde}", repetir)
                continue

            temp, umid, bat = r["temperatura"], r["umidade"], r["bateria"]
            if temp is not None:
                if temp <= t_min:
                    novos += _registrar(con, sid, ts, "geada", temp,
                                        f"{temp} C <= {t_min} C", repetir)
                elif temp >= t_max:
                    novos += _registrar(con, sid, ts, "calor_extremo", temp,
                                        f"{temp} C >= {t_max} C", repetir)
            if umid is not None:
                if umid <= u_min:
                    novos += _registrar(con, sid, ts, "umidade_baixa", umid, None, repetir)
                elif umid >= u_max:
                    novos += _registrar(con, sid, ts, "umidade_alta", umid, None, repetir)
            if bat is not None and bat <= bat_min:
                novos += _registrar(con, sid, ts, "bateria_baixa", bat,
                                    f"bateria em {bat}%", repetir)

        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return novos


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    cfg = Config()
    con = conectar(cfg.txt("banco", "caminho"))
    inicializar(con)
    n = detectar(con, cfg)
    print(f"{n} evento(s) novo(s)")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
