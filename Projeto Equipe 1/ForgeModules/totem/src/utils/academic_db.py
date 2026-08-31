import sqlite3
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

_sync_lock = threading.Lock()
_last_sync_time: float = 0
_db_initialized: bool = False

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "academic.db")

def init_db():
    """Initialize the SQLite academic database tables."""
    global _db_initialized
    if _db_initialized and os.path.exists(DB_PATH):
        return

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Table for Professors
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS professors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            room TEXT NOT NULL,
            email TEXT,
            department TEXT
        )
    """)
    
    # 2. Table for Class Schedules
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            weekday INTEGER NOT NULL, -- 0=Monday, ..., 6=Sunday
            start_time TEXT NOT NULL,  -- HH:MM
            end_time TEXT NOT NULL,    -- HH:MM
            room TEXT NOT NULL,
            teacher_name TEXT
        )
    """)
    
    # 3. Table for Events and News
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            link TEXT,
            pub_date TEXT,
            category TEXT,
            is_event BOOLEAN DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()
    _db_initialized = True
    logger.info("Academic database initialized at %s", DB_PATH)

def save_professor(name: str, room: str, email: str = None, department: str = None):
    """Save or update a professor's info."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO professors (name, room, email, department)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            room = excluded.room,
            email = excluded.email,
            department = excluded.department
    """, (name, room, email, department))
    conn.commit()
    conn.close()

def save_schedule(subject: str, weekday: int, start_time: str, end_time: str, room: str, teacher_name: str = None):
    """Save a class schedule slot."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Check if slot exists to prevent duplicates
    cursor.execute("""
        SELECT id FROM schedules 
        WHERE subject = ? AND weekday = ? AND start_time = ? AND room = ?
    """, (subject, weekday, start_time, room))
    row = cursor.fetchone()
    if not row:
        cursor.execute("""
            INSERT INTO schedules (subject, weekday, start_time, end_time, room, teacher_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (subject, weekday, start_time, end_time, room, teacher_name))
        conn.commit()
    conn.close()

def save_news_event(title: str, link: str, pub_date: str, category: str, is_event: bool = False):
    """Save a news or event item."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Check if item exists by title
    cursor.execute("SELECT id FROM news_events WHERE title = ?", (title,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("""
            INSERT INTO news_events (title, link, pub_date, category, is_event)
            VALUES (?, ?, ?, ?, ?)
        """, (title, link, pub_date, category, 1 if is_event else 0))
        conn.commit()
    conn.close()

def clear_schedules():
    """Clear all schedules to reload them."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM schedules")
    conn.commit()
    conn.close()

def get_professors() -> List[Dict[str, Any]]:
    """Retrieve list of all professors."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, room, email, department FROM professors ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return [{"name": r[0], "room": r[1], "email": r[2], "department": r[3]} for r in rows]

def get_recent_news_events(limit: int = 5) -> List[Dict[str, Any]]:
    """Retrieve recent news or events."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT title, link, pub_date, category, is_event FROM news_events ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{"title": r[0], "link": r[1], "pub_date": r[2], "category": r[3], "is_event": bool(r[4])} for r in rows]

def get_active_classes() -> List[Dict[str, Any]]:
    """Retrieve classes currently active based on current Brazil time."""
    if not os.path.exists(DB_PATH):
        return []
    
    # Brazil Time (UTC-3)
    tz_br = timezone(timedelta(hours=-3))
    now_br = datetime.now(timezone.utc).astimezone(tz_br)
    weekday = now_br.weekday()
    time_str = now_br.strftime("%H:%M")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT subject, start_time, end_time, room, teacher_name 
        FROM schedules 
        WHERE weekday = ? AND start_time <= ? AND end_time > ?
    """, (weekday, time_str, time_str))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [{"subject": r[0], "start_time": r[1], "end_time": r[2], "room": r[3], "teacher_name": r[4]} for r in rows]

def get_upcoming_classes_today() -> List[Dict[str, Any]]:
    """Retrieve upcoming classes today based on current Brazil time."""
    if not os.path.exists(DB_PATH):
        return []
    
    tz_br = timezone(timedelta(hours=-3))
    now_br = datetime.now(timezone.utc).astimezone(tz_br)
    weekday = now_br.weekday()
    time_str = now_br.strftime("%H:%M")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT subject, start_time, end_time, room, teacher_name 
        FROM schedules 
        WHERE weekday = ? AND start_time > ?
        ORDER BY start_time ASC
        LIMIT 5
    """, (weekday, time_str))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [{"subject": r[0], "start_time": r[1], "end_time": r[2], "room": r[3], "teacher_name": r[4]} for r in rows]

def sync_from_scraper():
    """Dynamically pull scraped data from the Scraping4Hackathon API and sync to local academic.db."""
    import urllib.request
    import json
    from src.utils.config_manager import ConfigManager
    
    cfg = ConfigManager.get_instance()
    custom_url = cfg.get_config("SYSTEM_OPTIONS.NETWORK.SCRAPER_API_URL")
    
    # Try custom, then fallback to local scraper instance
    endpoints = []
    if custom_url:
        endpoints.append(custom_url)
    endpoints.append("http://localhost:8000/dados-atuais")
    
    payload = None
    for url in endpoints:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'MinaAssistant/1.0'})
            with urllib.request.urlopen(req, timeout=1.5) as response:
                payload = json.loads(response.read().decode('utf-8'))
                if payload:
                    logger.debug("Connected to Scraping4Hackathon API at %s", url)
                    break
        except Exception:
            continue
            
    if not payload:
        return
        
    data = payload.get("data")
    if not data or "raw_payload" not in data:
        return
        
    raw = data["raw_payload"]
    
    # Extract data from raw payload
    news = raw.get("news", [])
    active_classes = raw.get("active_classes", [])
    upcoming_classes = raw.get("upcoming_classes", [])
    
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Sync News & Events using a single transaction
        # ⚡ Bolt: Batching news inserts to reduce DB connection overhead
        for n in news:
            title = n.get("title", "")
            link = n.get("link", "")
            pub_date = n.get("pub_date", "")
            category = ", ".join(n.get("categories", []))
            if title:
                cursor.execute("SELECT id FROM news_events WHERE title = ?", (title,))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO news_events (title, link, pub_date, category, is_event)
                        VALUES (?, ?, ?, ?, ?)
                    """, (title, link, pub_date, category, 0))

        # Sync Weekly schedules using the same transaction
        day_of_week = raw.get("day_of_week")
        if day_of_week is not None:
            # Clear old schedules for this weekday to keep it updated
            cursor.execute("DELETE FROM schedules WHERE weekday = ?", (day_of_week,))
            
            # ⚡ Bolt: Batching schedule inserts to reduce N+1 queries and connection overhead
            # Map time tuple (e.g. 8.0, 11.6) to HH:MM format
            for c in active_classes + upcoming_classes:
                time_range = c.get("time", (0.0, 0.0))
                start_h = int(time_range[0])
                start_m = int(round((time_range[0] - start_h) * 60))
                end_h = int(time_range[1])
                end_m = int(round((time_range[1] - end_h) * 60))
                
                start_time = f"{start_h:02d}:{start_m:02d}"
                end_time = f"{end_h:02d}:{end_m:02d}"
                
                subject = c.get("subject", "")
                room = c.get("room", "")
                teacher_name = c.get("teacher", "")

                cursor.execute("""
                    SELECT id FROM schedules
                    WHERE subject = ? AND weekday = ? AND start_time = ? AND room = ?
                """, (subject, day_of_week, start_time, room))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO schedules (subject, weekday, start_time, end_time, room, teacher_name)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (subject, day_of_week, start_time, end_time, room, teacher_name))

            logger.info("Successfully updated weekday %d schedules from Scraper API", day_of_week)

        # Commit all batched operations at once
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Failed to write scraped data to local database: %s", e)
    finally:
        conn.close()

def _throttled_sync():
    """Wrapper that updates _last_sync_time and releases the lock after sync."""
    global _last_sync_time
    try:
        sync_from_scraper()
    finally:
        _last_sync_time = time.monotonic()
        _sync_lock.release()


def get_academic_context(user_query: str = None) -> str:
    """Format SQLite database tables into a prompt-friendly context text block, 
    dynamically filtering schedules based on the user's query keywords to save tokens."""
    # Throttled sync: max once per 60s, skip if already running
    if time.monotonic() - _last_sync_time > 60:
        if _sync_lock.acquire(blocking=False):
            threading.Thread(target=_throttled_sync, daemon=True).start()

    if not os.path.exists(DB_PATH):
        return "Nenhum dado acadêmico da UNESP disponível no momento."
        
    tz_br = timezone(timedelta(hours=-3))
    now_br = datetime.now(timezone.utc).astimezone(tz_br)
    today_weekday = now_br.weekday()
    
    # 1. Parse weekday filter from user query
    target_weekday = None
    query_lower = user_query.lower() if user_query else ""
    
    weekday_map = {
        "segunda": 0, "segundão": 0, "monday": 0,
        "terça": 1, "tercinha": 1, "tuesday": 1,
        "quarta": 2, "wednesday": 2,
        "quinta": 3, "thursday": 3,
        "sexta": 4, "friday": 4,
        "sábado": 5, "sabado": 5, "saturday": 5,
        "domingo": 6, "sunday": 6
    }
    
    for kw, val in weekday_map.items():
        if kw in query_lower:
            target_weekday = val
            break
            
    if "amanhã" in query_lower or "amanha" in query_lower or "tomorrow" in query_lower:
        target_weekday = (today_weekday + 1) % 7
    elif "ontem" in query_lower or "yesterday" in query_lower:
        target_weekday = (today_weekday - 1) % 7
        
    # Determine if we should show the whole week
    show_all_week = any(x in query_lower for x in ["semana", "mês", "mes", "todos", "todas", "agenda", "calendário", "calendario"])
    
    parts = []
    parts.append("=== CONTEXTO ACADÊMICO ATUAL DA UNESP SOROCABA (Mina Local DB) ===")
    parts.append(f"Data/Hora do Sistema: {now_br.strftime('%d/%m/%Y %H:%M')} (Horário de Brasília)")
    
    # Active Classes Right Now
    active = get_active_classes()
    if active:
        parts.append("\n[Aulas em Andamento Agora]:")
        for a in active:
            parts.append(f"- Matéria: {a['subject']} | Horário: {a['start_time']} às {a['end_time']} | Sala: {a['room']} | Prof: {a['teacher_name']}")
            
    # Fetch schedules based on dynamic RAG query
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    weekday_names = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    
    if show_all_week:
        parts.append("\n[Cronograma Completo de Aulas da Semana]:")
        cursor.execute("SELECT subject, weekday, start_time, end_time, room, teacher_name FROM schedules ORDER BY weekday, start_time")
        rows = cursor.fetchall()
        for r in rows:
            parts.append(f"- {weekday_names[r[1]]}: {r[0]} ({r[2]}-{r[3]}) | Sala: {r[4]} | Prof: {r[5]}")
    elif target_weekday is not None:
        parts.append(f"\n[Aulas Filtradas para {weekday_names[target_weekday]}]:")
        cursor.execute("SELECT subject, start_time, end_time, room, teacher_name FROM schedules WHERE weekday = ? ORDER BY start_time", (target_weekday,))
        rows = cursor.fetchall()
        if rows:
            for r in rows:
                parts.append(f"- Matéria: {r[0]} | Horário: {r[1]} às {r[2]} | Sala: {r[3]} | Prof: {r[4]}")
        else:
            parts.append("- Nenhuma aula cadastrada para este dia.")
    else:
        # Default: show upcoming today
        upcoming = get_upcoming_classes_today()
        if upcoming:
            parts.append("\n[Próximas Aulas de Hoje]:")
            for u in upcoming:
                parts.append(f"- Matéria: {u['subject']} | Início: {u['start_time']} | Sala: {u['room']} | Prof: {u['teacher_name']}")
                
    conn.close()
            
    # 3. Professors Rooms list
    profs = get_professors()
    if profs:
        parts.append("\n[Localização de Professores e Salas]:")
        for p in profs:
            parts.append(f"- {p['name']}: {p['room']} (E-mail: {p['email'] or 'Não informado'})")
            
    # 4. News & Events
    news = get_recent_news_events(5)
    if news:
        parts.append("\n[Mural e Notícias do Jornal da Unesp]:")
        for n in news:
            type_str = "Evento" if n['is_event'] else "Notícia"
            parts.append(f"- [{type_str}] {n['title']} (Categoria: {n['category'] or 'Geral'})")
            
    return "\n".join(parts)
