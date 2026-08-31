import time
from src.utils.academic_db import save_schedule, init_db, DB_PATH
import sqlite3

def run_test():
    init_db()
    # Test N+1 saves
    start = time.time()
    for i in range(100):
        save_schedule(f"Subject {i}", 1, "08:00", "10:00", f"Room {i}")
    end = time.time()
    print(f"N+1 time: {end - start:.4f}s")

    # Test batch saves
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    start = time.time()
    for i in range(100, 200):
        subject = f"Subject {i}"
        weekday = 1
        start_time = "08:00"
        end_time = "10:00"
        room = f"Room {i}"
        teacher_name = None
        cursor.execute("""
            SELECT id FROM schedules
            WHERE subject = ? AND weekday = ? AND start_time = ? AND room = ?
        """, (subject, weekday, start_time, room))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO schedules (subject, weekday, start_time, end_time, room, teacher_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (subject, weekday, start_time, end_time, room, teacher_name))
    conn.commit()
    conn.close()
    end = time.time()
    print(f"Batch time: {end - start:.4f}s")

if __name__ == "__main__":
    run_test()
