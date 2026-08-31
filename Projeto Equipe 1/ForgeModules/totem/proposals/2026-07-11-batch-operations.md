# Implement Batch Operations for Academic Database Seeding

## Summary
Replace the single-row `INSERT` operations in `src/utils/academic_db.py` (specifically `save_professor` and `save_schedule`) with batch operations (`executemany`) to improve seeding performance and reduce SQLite I/O overhead.

## Problem
Currently, when `scripts/unesp_scraper.py` seeds the database, it loops through the academic data and calls `save_professor` or `save_schedule` for each item. Each call opens a new connection, executes a single `INSERT`, commits the transaction, and closes the connection. This results in significant overhead and `N+1` query performance issues when seeding large amounts of data.

## Evidence
In `src/utils/academic_db.py`:
- `save_professor()` (lines 66-78) opens a connection, executes a single query, and commits.
- `save_schedule()` (lines 80-101) does the same.
- In `scripts/unesp_scraper.py`, a loop calls these functions sequentially (lines 127-147), establishing a new connection per row.

## Proposed Solution
Create batch functions in `src/utils/academic_db.py` (e.g., `save_professors_batch` and `save_schedules_batch`) that accept lists of dictionaries. These functions should open a single connection, use `cursor.executemany` (or loop over statements within a single transaction), commit once, and close the connection. Update `scripts/unesp_scraper.py` to use these new batch functions.

## Benefits
- **Performance:** Significantly reduces the time required to seed the database, especially when the number of professors or schedule slots grows.
- **Resource Efficiency:** Minimizes SQLite connection overhead and file I/O operations.

## Trade-offs
- Modifies the API surface of `academic_db.py`, requiring changes to the scraper logic.
- Potential complexity if a single row insertion fails within a batch.

## Risks
- Transaction deadlocks if multiple processes attempt to write batches concurrently, although the scraper is typically run sequentially.

## Estimated Complexity
- Low

## Priority
- Medium

## Success Criteria
- The seeder uses a single transaction (or a minimal number of transactions) for inserting lists of academic data.
- Noticeable reduction in execution time when running `scripts/unesp_scraper.py`.

## Open Questions
- Should we retain the single-row functions for one-off updates, or refactor all inserts to strictly use the batch methods?
