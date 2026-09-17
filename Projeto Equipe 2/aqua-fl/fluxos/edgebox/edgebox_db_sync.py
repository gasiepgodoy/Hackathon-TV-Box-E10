import json
import sqlite3
from pathlib import Path

from config import DATABASE_DIR, EDGEBOX_DATA_DIR

DB_PATH = DATABASE_DIR / "edgebox.db"
METRICS_PATH = EDGEBOX_DATA_DIR / "edgebox_metrics.jsonl"
MODEL_PATH = EDGEBOX_DATA_DIR / "edgebox_model_update.json"

AE_LATEST_PATH = EDGEBOX_DATA_DIR / "edgebox_autoencoder_latest.json"
AE_MODEL_PATH = EDGEBOX_DATA_DIR / "edgebox_autoencoder_model.json"
AE_UPDATE_PATH = EDGEBOX_DATA_DIR / "edgebox_autoencoder_update.json"


def connect():
    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT UNIQUE,
            node_id TEXT,
            cpu_percent REAL,
            ram_percent REAL,
            temperature_c REAL,
            disk_percent REAL,
            latency_ms REAL,
            load1 REAL,
            inferred_risk REAL,
            status TEXT,
            uptime_seconds INTEGER,
            rx_kbps REAL,
            tx_kbps REAL,
            raw_json TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            node_id TEXT,
            model_type TEXT,
            samples INTEGER,
            weights_json TEXT,
            raw_json TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS autoencoder_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT UNIQUE,
            node_id TEXT,
            status TEXT,
            reconstruction_error REAL,
            threshold REAL,
            anomaly_score REAL,
            input_vector_json TEXT,
            reconstruction_json TEXT,
            raw_json TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS autoencoder_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trained_at TEXT,
            created_at TEXT,
            model_type TEXT,
            input_size INTEGER,
            hidden_size INTEGER,
            samples INTEGER,
            train_error_mean REAL,
            train_error_std REAL,
            train_error_p95 REAL,
            threshold REAL,
            features_json TEXT,
            weights_json TEXT,
            raw_json TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS autoencoder_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            node_id TEXT,
            model_type TEXT,
            samples INTEGER,
            threshold REAL,
            features_json TEXT,
            weights_json TEXT,
            raw_json TEXT
        )
    """)

    return conn


def sync_metrics(conn):
    if not METRICS_PATH.exists():
        return 0

    inserted = 0

    with METRICS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                data = json.loads(line)
            except Exception:
                continue

            cur = conn.execute("""
                INSERT OR IGNORE INTO metrics (
                    timestamp,
                    node_id,
                    cpu_percent,
                    ram_percent,
                    temperature_c,
                    disk_percent,
                    latency_ms,
                    load1,
                    inferred_risk,
                    status,
                    uptime_seconds,
                    rx_kbps,
                    tx_kbps,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("timestamp"),
                data.get("node_id"),
                data.get("cpu_percent"),
                data.get("ram_percent"),
                data.get("temperature_c"),
                data.get("disk_percent"),
                data.get("latency_ms"),
                data.get("load1"),
                data.get("inferred_risk"),
                data.get("status"),
                data.get("uptime_seconds"),
                data.get("rx_kbps"),
                data.get("tx_kbps"),
                json.dumps(data, ensure_ascii=False),
            ))

            inserted += cur.rowcount

    return inserted


def sync_model_update(conn):
    if not MODEL_PATH.exists():
        return 0

    try:
        data = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0

    cur = conn.execute("""
        INSERT INTO model_updates (
            created_at,
            node_id,
            model_type,
            samples,
            weights_json,
            raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        data.get("created_at"),
        data.get("node_id"),
        data.get("model_type"),
        data.get("samples") or data.get("samples_total"),
        json.dumps(data.get("weights", []), ensure_ascii=False),
        json.dumps(data, ensure_ascii=False),
    ))

    return cur.rowcount


def sync_autoencoder_result(conn):
    if not AE_LATEST_PATH.exists():
        return 0

    try:
        data = json.loads(AE_LATEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0

    cur = conn.execute("""
        INSERT OR IGNORE INTO autoencoder_results (
            created_at,
            node_id,
            status,
            reconstruction_error,
            threshold,
            anomaly_score,
            input_vector_json,
            reconstruction_json,
            raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("created_at"),
        data.get("node_id"),
        data.get("status"),
        data.get("reconstruction_error"),
        data.get("threshold"),
        data.get("anomaly_score"),
        json.dumps(data.get("input_vector", []), ensure_ascii=False),
        json.dumps(data.get("reconstruction", []), ensure_ascii=False),
        json.dumps(data, ensure_ascii=False),
    ))

    return cur.rowcount


def sync_autoencoder_model(conn):
    if not AE_MODEL_PATH.exists():
        return 0

    try:
        data = json.loads(AE_MODEL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0

    weights = {
        "W1": data.get("W1", []),
        "b1": data.get("b1", []),
        "W2": data.get("W2", []),
        "b2": data.get("b2", []),
    }

    cur = conn.execute("""
        INSERT INTO autoencoder_models (
            trained_at,
            created_at,
            model_type,
            input_size,
            hidden_size,
            samples,
            train_error_mean,
            train_error_std,
            train_error_p95,
            threshold,
            features_json,
            weights_json,
            raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("trained_at"),
        data.get("created_at"),
        data.get("model_type"),
        data.get("input_size"),
        data.get("hidden_size"),
        data.get("samples"),
        data.get("train_error_mean"),
        data.get("train_error_std"),
        data.get("train_error_p95"),
        data.get("threshold"),
        json.dumps(data.get("features", []), ensure_ascii=False),
        json.dumps(weights, ensure_ascii=False),
        json.dumps(data, ensure_ascii=False),
    ))

    return cur.rowcount


def sync_autoencoder_update(conn):
    if not AE_UPDATE_PATH.exists():
        return 0

    try:
        data = json.loads(AE_UPDATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0

    cur = conn.execute("""
        INSERT INTO autoencoder_updates (
            created_at,
            node_id,
            model_type,
            samples,
            threshold,
            features_json,
            weights_json,
            raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("created_at"),
        data.get("node_id"),
        data.get("model_type"),
        data.get("samples"),
        data.get("threshold"),
        json.dumps(data.get("features", []), ensure_ascii=False),
        json.dumps(data.get("weights", {}), ensure_ascii=False),
        json.dumps(data, ensure_ascii=False),
    ))

    return cur.rowcount


def main():
    conn = connect()

    metrics_count = sync_metrics(conn)
    model_count = sync_model_update(conn)
    ae_result_count = sync_autoencoder_result(conn)
    ae_model_count = sync_autoencoder_model(conn)
    ae_update_count = sync_autoencoder_update(conn)

    conn.commit()
    conn.close()

    print(
        "Banco atualizado | "
        f"métricas novas: {metrics_count} | "
        f"modelo linear: {model_count} | "
        f"autoencoder resultados: {ae_result_count} | "
        f"autoencoder modelos: {ae_model_count} | "
        f"autoencoder updates: {ae_update_count}"
    )


if __name__ == "__main__":
    main()
