## 2024-05-14 - SQLite Database Batch Inserts Optimization
**Learning:** Calling individual INSERT functions inside a loop, where each call opens a new database connection, does a SELECT query, and commits, introduces a severe N+1 problem. I identified this bottleneck in `sync_from_scraper` in `src/utils/academic_db.py`. Testing shows a 40x speedup when moving the queries to a single batch inside the loop rather than opening/closing per item.
**Action:** Replace `save_schedule` and `save_news_event` inside `sync_from_scraper` with batch operations that reuse a single connection and commit once, to vastly reduce I/O.

## 2024-05-14 - PyTest PortAudio dependencies and Qt Platform plugins in Headless Mode
**Learning:** Pytest relies on the `sounddevice` package, which inherently calls upon the C `libportaudio` dependency directly, bypassing virtual environments. If missing, `tests_all.py` crashes entirely since models import everything dynamically. GUI tests in a headless environment also often fail due to hardcoded absolute paths to the project root in test subprocesses, and xvfb needs Qt dependencies (like `libxcb-cursor0`, etc) configured properly.
**Action:** Always install system packages `portaudio19-dev` and verify `pytest` execution path points inside pipx or the activated environment to prevent missing packages. Dynamically resolve `cwd` path using `os.path.dirname` when spawning Python subprocess tests.

## 2024-07-10 - Reusing HTTP Sessions for Real-Time TTS
**Learning:** The codebase repeatedly creates an `aiohttp.ClientSession` for each audio chunk request during real-time TTS. This adds significant overhead (TCP and TLS handshake latency) to each synthesis request, which severely impacts response times for small audio chunks.
**Action:** Reuse a single `aiohttp.ClientSession` across multiple requests by initializing it in the client instance and tearing it down only when the client is closed.
