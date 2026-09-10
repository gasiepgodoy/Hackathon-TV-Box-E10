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


# Colunas acrescentadas depois da versao inicial. Bancos ja em producao na box
# nao sao recriados pelo schema.sql (que usa CREATE TABLE IF NOT EXISTS), entao
# precisam de ALTER TABLE.
_MIGRACOES = [
    ("leituras",  "pressao",     "REAL"),
    ("sensores",  "transporte",  "TEXT NOT NULL DEFAULT 'zigbee'"),
    ("agregados", "press_media", "REAL"),
]


def migrar(con: sqlite3.Connection) -> list[str]:
    """Acrescenta colunas que faltam. Idempotente: rodar de novo nao faz nada."""
    aplicadas = []
    for tabela, coluna, tipo in _MIGRACOES:
        existentes = {r["name"] for r in con.execute(f"PRAGMA table_info({tabela})")}
        if existentes and coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
            aplicadas.append(f"{tabela}.{coluna}")
    return aplicadas


def inicializar(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    migrar(con)


def id_sensor(con: sqlite3.Connection, ieee: str, modelo: str | None = None,
              transporte: str = "zigbee") -> int:
    """Retorna o id do sensor, cadastrando-o na primeira vez que aparecer."""
    row = con.execute("SELECT id FROM sensores WHERE ieee = ?", (ieee,)).fetchone()
    if row:
        return row["id"]
    cur = con.execute(
        "INSERT INTO sensores (ieee, nome, modelo, transporte) VALUES (?, ?, ?, ?)",
        (ieee, ieee, modelo, transporte),
    )
    return int(cur.lastrowid)


def gravar_leituras(con: sqlite3.Connection, linhas: list[dict]) -> int:
    """Grava um lote de leituras.

    Cada item e um dict com 'ieee' e 'ts' obrigatorios; temperatura, umidade,
    pressao, bateria, linkquality e transporte sao opcionais. Usamos dict em vez
    de tupla porque as duas origens (Zigbee e LoRa) trazem campos diferentes.

    Uma transacao unica por lote — e isso que poupa o cartao SD.
    """
    if not linhas:
        return 0
    con.execute("BEGIN")
    try:
        prontas = [
            (
                id_sensor(con, l["ieee"], l.get("modelo"), l.get("transporte", "zigbee")),
                l["ts"],
                l.get("temperatura"),
                l.get("umidade"),
                l.get("pressao"),
                l.get("bateria"),
                l.get("linkquality"),
            )
            for l in linhas
        ]
        con.executemany(
            "INSERT INTO leituras"
            " (sensor_id, ts, temperatura, umidade, pressao, bateria, linkquality)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
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
