"""Acesso ao banco SQLite do hub."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


def conectar(caminho: str | Path) -> sqlite3.Connection:
    """Abre (criando se preciso) o banco com os pragmas de durabilidade/desgaste."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(caminho), timeout=30.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    # NORMAL + WAL: sobrevive a queda de processo e reduz muito a escrita
    # fisica no cartao SD em relacao ao FULL padrao.
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 30000")
    return con


def inicializar(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text(encoding="utf-8"))


def id_sensor(con: sqlite3.Connection, ieee: str, modelo: str | None = None) -> int:
    """Retorna o id do sensor, cadastrando-o na primeira vez que aparecer."""
    row = con.execute("SELECT id FROM sensores WHERE ieee = ?", (ieee,)).fetchone()
    if row:
        return row["id"]
    cur = con.execute(
        "INSERT INTO sensores (ieee, nome, modelo) VALUES (?, ?, ?)",
        (ieee, ieee, modelo),
    )
    return int(cur.lastrowid)


def gravar_leituras(con: sqlite3.Connection, linhas: list[tuple]) -> int:
    """Grava um lote de leituras.

    Cada linha: (ieee, ts, temperatura, umidade, bateria, linkquality).
    Uma transacao unica por lote — e isso que poupa o cartao.
    """
    if not linhas:
        return 0
    con.execute("BEGIN")
    try:
        prontas = [
            (id_sensor(con, ieee), ts, temp, umid, bat, lqi)
            for (ieee, ts, temp, umid, bat, lqi) in linhas
        ]
        con.executemany(
            "INSERT INTO leituras (sensor_id, ts, temperatura, umidade, bateria, linkquality)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            prontas,
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(prontas)


def purgar(con: sqlite3.Connection, dias: int, agora: int | None = None) -> int:
    """Apaga leituras brutas antigas. Agregados e eventos sao preservados."""
    import time

    agora = agora if agora is not None else int(time.time())
    corte = agora - dias * 86400
    cur = con.execute("DELETE FROM leituras WHERE ts < ?", (corte,))
    return cur.rowcount or 0
