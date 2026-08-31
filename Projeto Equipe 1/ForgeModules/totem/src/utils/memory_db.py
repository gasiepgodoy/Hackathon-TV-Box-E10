import sqlite3
import os
from typing import List, Tuple
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "memory.db")
_db_initialized: bool = False

def init_db():
    """Initialize the SQLite memories database."""
    global _db_initialized
    if _db_initialized and os.path.exists(DB_PATH):
        return

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            keypoint TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()
    _db_initialized = True
    logger.info("Memories database initialized at %s", DB_PATH)

def save_memory(username: str, keypoint: str):
    """Save a new memory keypoint, updating it if it already exists, or deleting if keypoint is 'DELETE'."""
    init_db()  # Ensure DB is created
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    username = username.strip()
    keypoint = keypoint.strip()
    
    if keypoint.upper() == "DELETE":
        cursor.execute("DELETE FROM memories WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        logger.info("Deleted all memories for user: %s", username)
        return

    # Check if any memories already exist for this username
    cursor.execute("SELECT id FROM memories WHERE username = ? ORDER BY timestamp DESC", (username,))
    rows = cursor.fetchall()
    
    if rows:
        # Update the most recent one and delete any duplicates
        primary_id = rows[0][0]
        cursor.execute("UPDATE memories SET keypoint = ?, timestamp = CURRENT_TIMESTAMP WHERE id = ?", (keypoint, primary_id))
        if len(rows) > 1:
            other_ids = [r[0] for r in rows[1:]]
            cursor.execute(f"DELETE FROM memories WHERE id IN ({','.join('?' for _ in other_ids)})", other_ids)
        conn.commit()
        logger.info("Updated memory and cleaned duplicates: [%s] -> %s", username, keypoint)
    else:
        cursor.execute("INSERT INTO memories (username, keypoint) VALUES (?, ?)", (username, keypoint))
        conn.commit()
        logger.info("Saved memory: [%s] -> %s", username, keypoint)
        
    conn.close()

def get_all_memories() -> List[Tuple[str, str]]:
    """Retrieve all saved memories."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT username, keypoint FROM memories ORDER BY timestamp DESC LIMIT 50")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as exc:
        logger.error("Failed to retrieve memories: %s", exc)
        return []

def save_setting(key: str, value: str):
    """Save a setting key-value pair, updating if it exists."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
    logger.debug("Saved setting: %s = %s", key, value)

def get_setting(key: str):
    """Retrieve a setting value by key."""
    if not os.path.exists(DB_PATH):
        return None
    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as exc:
        logger.error("Failed to retrieve setting %s: %s", key, exc)
        return None
