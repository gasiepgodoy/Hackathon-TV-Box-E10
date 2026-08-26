"""Agregador: condensa leituras brutas em resumos por janela.

E o resumo que viaja pelo LoRa. Guardamos min/max alem da media porque um
evento curto (uma geada de 20 minutos) desaparece numa media horaria — e e
exatamente esse evento que o projeto precisa capturar.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
import time

from .config import Config
from .db import conectar, inicializar

log = logging.getLogger("hub.agregador")


def agregar(con: sqlite3.Connection, janela_s: int, agora: int | None = None) -> int:
    """Gera agregados das janelas ja encerradas. Idempotente."""
    agora = agora if agora is not None else int(time.time())
    limite = (agora // janela_s) * janela_s   # inicio da janela corrente: ainda aberta

    linhas = con.execute(
        """
        SELECT sensor_id,
               (ts / :j) * :j       AS inicio,
               MIN(temperatura)     AS temp_min,
               MAX(temperatura)     AS temp_max,
               AVG(temperatura)     AS temp_media,
               MIN(umidade)         AS umid_min,
               MAX(umidade)         AS umid_max,
               AVG(umidade)         AS umid_media,
               MIN(bateria)         AS bateria,
               COUNT(*)             AS amostras
          FROM leituras
         WHERE ts < :limite
         GROUP BY sensor_id, inicio
        """,
        {"j": janela_s, "limite": limite},
    ).fetchall()

    if not linhas:
        return 0

    con.execute("BEGIN")
    try:
        for r in linhas:
            # ON CONFLICT com guarda `enviado = 0`: reprocessar uma janela nao
            # reenfileira o que ja subiu pelo LoRa.
            con.execute(
                """
                INSERT INTO agregados
                    (sensor_id, inicio, temp_min, temp_max, temp_media,
                     umid_min, umid_max, umid_media, bateria, amostras)
                VALUES (:sensor_id, :inicio, :temp_min, :temp_max, :temp_media,
                        :umid_min, :umid_max, :umid_media, :bateria, :amostras)
                ON CONFLICT(sensor_id, inicio) DO UPDATE SET
                    temp_min   = excluded.temp_min,
                    temp_max   = excluded.temp_max,
                    temp_media = excluded.temp_media,
                    umid_min   = excluded.umid_min,
                    umid_max   = excluded.umid_max,
                    umid_media = excluded.umid_media,
                    bateria    = excluded.bateria,
                    amostras   = excluded.amostras
                WHERE agregados.enviado = 0
                """,
                dict(r),
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    log.info("%d janelas agregadas", len(linhas))
    return len(linhas)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    cfg = Config()
    con = conectar(cfg.txt("banco", "caminho"))
    inicializar(con)
    agregar(con, cfg.num("agregador", "janela_s"))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
