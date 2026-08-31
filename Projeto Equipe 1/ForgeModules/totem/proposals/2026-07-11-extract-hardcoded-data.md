# Extract Hardcoded Academic Data

## Summary
Extract the hardcoded `PROFESSORS_DATA` and `SCHEDULES_DATA` dictionaries from `scripts/unesp_scraper.py` into a standalone JSON or YAML configuration file.

## Problem
The `scripts/unesp_scraper.py` file currently contains large lists of dictionaries (`PROFESSORS_DATA` and `SCHEDULES_DATA`) directly in the source code. This mixes configuration with code, making it harder for non-developers to update academic schedules and professor information without touching Python scripts.

## Evidence
In `scripts/unesp_scraper.py`:
- `PROFESSORS_DATA` is hardcoded around line 21.
- `SCHEDULES_DATA` is hardcoded around line 33.
Although the script later tries to load from `config/academic_data.json`, the hardcoded fallbacks in the script add unnecessary length to the code and create a secondary source of truth.

## Proposed Solution
Move the default contents of `PROFESSORS_DATA` and `SCHEDULES_DATA` into the `config/academic_data.json` file by default (or a new default configuration file). Remove the hardcoded lists from `scripts/unesp_scraper.py`, replacing them with logic that strictly loads from the configuration file.

## Benefits
- **Maintainability:** Clear separation between logic and data.
- **Usability:** Non-technical staff can update schedules by editing a JSON file without risking syntax errors in Python code.
- **Cleanliness:** Reduces the size of `scripts/unesp_scraper.py` by removing boilerplate data.

## Trade-offs
- The scraper will hard fail if the configuration file is missing or invalid, requiring a robust default file to be present in the repository.

## Risks
- Incorrect JSON formatting during manual updates could break the scraper if not validated properly.

## Estimated Complexity
- Low

## Priority
- Medium

## Success Criteria
- `scripts/unesp_scraper.py` no longer contains the hardcoded lists.
- The scraper successfully runs and populates the database using only the external configuration file.

## Open Questions
- Should we provide a JSON schema to help users validate `academic_data.json` before running the scraper?
