"""
Cadastro de sensores em SQLite.

Esse banco guarda apenas os METADADOS dos sensores (nome, protocolo,
config de conexão, etc). Os dados que os sensores geram (as leituras)
vão para o InfluxDB, nunca para cá.
"""
import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional

from .config import settings
from .models import Sensor, SensorCreate, SensorUpdate

_lock = threading.Lock()


def _row_to_sensor(row: sqlite3.Row) -> Sensor:
    return Sensor(
        id=row["id"],
        nome=row["nome"],
        tipo=row["tipo"],
        protocolo=row["protocolo"],
        unidade=row["unidade"],
        local=row["local"],
        limite_min=row["limite_min"],
        limite_max=row["limite_max"],
        config=json.loads(row["config"]),
        ativo=bool(row["ativo"]),
        criado_em=row["criado_em"],
        status=row["status"],
        ultimo_erro=row["ultimo_erro"],
    )


@contextmanager
def _conn():
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def iniciar_banco() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sensores (
                id TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                tipo TEXT NOT NULL,
                protocolo TEXT NOT NULL,
                unidade TEXT,
                local TEXT,
                limite_min REAL,
                limite_max REAL,
                config TEXT NOT NULL DEFAULT '{}',
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'parado',
                ultimo_erro TEXT
            )
            """
        )
        # Migração para bancos criados antes dos limites operacionais existirem.
        # Sem isso, atualizar o gateway quebraria uma instalação em uso.
        colunas = {linha["name"] for linha in conn.execute("PRAGMA table_info(sensores)")}
        for coluna in ("limite_min", "limite_max"):
            if coluna not in colunas:
                conn.execute(f"ALTER TABLE sensores ADD COLUMN {coluna} REAL")


def listar_sensores() -> list[Sensor]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM sensores ORDER BY criado_em DESC").fetchall()
        return [_row_to_sensor(r) for r in rows]


def obter_sensor(sensor_id: str) -> Optional[Sensor]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM sensores WHERE id = ?", (sensor_id,)).fetchone()
        return _row_to_sensor(row) if row else None


def criar_sensor(dados: SensorCreate) -> Sensor:
    sensor = Sensor.novo(dados)
    with _lock, _conn() as conn:
        conn.execute(
            """INSERT INTO sensores (id, nome, tipo, protocolo, unidade, local, limite_min, limite_max, config, ativo, criado_em, status, ultimo_erro)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sensor.id, sensor.nome, sensor.tipo, sensor.protocolo, sensor.unidade,
                sensor.local, sensor.limite_min, sensor.limite_max, json.dumps(sensor.config), int(sensor.ativo),
                sensor.criado_em, sensor.status, sensor.ultimo_erro,
            ),
        )
    return sensor


def atualizar_sensor(sensor_id: str, dados: SensorUpdate) -> Optional[Sensor]:
    atual = obter_sensor(sensor_id)
    if not atual:
        return None
    novos = atual.model_copy(update={k: v for k, v in dados.model_dump(exclude_unset=True).items()})
    with _lock, _conn() as conn:
        conn.execute(
            """UPDATE sensores SET nome=?, tipo=?, protocolo=?, unidade=?, local=?, limite_min=?, limite_max=?, config=?, ativo=?
               WHERE id=?""",
            (
                novos.nome, novos.tipo, novos.protocolo, novos.unidade, novos.local,
                novos.limite_min, novos.limite_max, json.dumps(novos.config), int(novos.ativo), sensor_id,
            ),
        )
    return novos


def atualizar_status(sensor_id: str, status: str, ultimo_erro: Optional[str] = None) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE sensores SET status=?, ultimo_erro=? WHERE id=?",
            (status, ultimo_erro, sensor_id),
        )


def remover_sensor(sensor_id: str) -> bool:
    with _lock, _conn() as conn:
        cur = conn.execute("DELETE FROM sensores WHERE id=?", (sensor_id,))
        return cur.rowcount > 0
