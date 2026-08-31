# Decouple Intent Classifier from Direct SQLite I/O

## Summary
The MABI Intent Classifier performs synchronous SQLite operations on the main event loop when querying `academic.db`, which can block the asyncio event loop and degrade system responsiveness during heavy database operations.

## Problem
In `src/utils/intent_classifier.py` and `src/utils/academic_db.py`, the system performs SQLite database queries synchronously. If the application is running under `asyncio` (like `main_gui.py` running the PyQt event loop asynchronously with `qasync`), blocking operations like database lookups can freeze the UI and delay STT/TTS processing.

## Evidence
- `src/utils/academic_db.py` contains standard `sqlite3` API usage with `cursor.execute(...)` that executes synchronously.
- `src/utils/chat_bridge.py` calls `get_academic_context(prompt)` synchronously inside `_get_system_prompt_with_memories`.
- The Memory constraints explicitly state: "To prevent blocking the asyncio event loop, synchronous CPU-bound operations... should be offloaded to a background worker thread using `asyncio.to_thread`."

## Proposed Solution
Wrap the database access layers (`academic_db.py` and `memory_db.py`) with asynchronous interfaces that utilize `asyncio.to_thread` for all disk I/O and query execution, ensuring the main event loop remains unblocked.

## Benefits
- Increased GUI responsiveness.
- Improved audio pipeline performance without stuttering.
- Scalability to larger datasets in `academic.db` without UX degradation.

## Trade-offs
- Refactoring synchronous call sites across the application to handle async/await.

## Risks
- Potential race conditions if thread safety is not maintained for SQLite connections (e.g. need to use thread-local connections or a dedicated DB thread).

## Estimated Complexity
- Medium

## Priority
- High

## Success Criteria
- Long database queries do not delay QML UI animations or STT chunk processing.

## Open Questions
- Should we use `aiosqlite` instead of `asyncio.to_thread` with standard `sqlite3` for a more idiomatic async database layer?
