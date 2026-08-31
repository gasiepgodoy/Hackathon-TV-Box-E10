import re

with open("src/utils/academic_db.py", "r") as f:
    content = f.read()

# Add _last_sync_time and _sync_lock
if "_last_sync_time =" not in content:
    content = content.replace("logger = get_logger(__name__)", "logger = get_logger(__name__)\n\n_last_sync_time = 0.0\n_sync_lock = False")

old_get_context = """def get_academic_context(user_query: str = None) -> str:
    \"\"\"Format SQLite database tables into a prompt-friendly context text block,
    dynamically filtering schedules based on the user's query keywords to save tokens.\"\"\"
    import threading
    # Fire off database synchronization in the background
    threading.Thread(target=sync_from_scraper, daemon=True).start()"""

new_get_context = """def get_academic_context(user_query: str = None) -> str:
    \"\"\"Format SQLite database tables into a prompt-friendly context text block,
    dynamically filtering schedules based on the user's query keywords to save tokens.\"\"\"
    import threading
    import time

    global _last_sync_time, _sync_lock
    # Fire off database synchronization in the background, max once per 60 seconds
    if not _sync_lock and time.time() - _last_sync_time > 60:
        _sync_lock = True

        def _sync_worker():
            global _last_sync_time, _sync_lock
            try:
                sync_from_scraper()
                _last_sync_time = time.time()
            finally:
                _sync_lock = False

        threading.Thread(target=_sync_worker, daemon=True).start()"""

if old_get_context in content:
    content = content.replace(old_get_context, new_get_context)
else:
    print("Could not find get_academic_context signature")

with open("src/utils/academic_db.py", "w") as f:
    f.write(content)
