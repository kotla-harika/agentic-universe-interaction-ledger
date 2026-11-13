
# Submission

## Candidate
- **Name:** Kotla Harika
- **Assignment chosen:** Interaction Ledger & Reporting Pipeline (Data) project A
- **Time spent:** [Approximately 10 hours]

## How to run

From the project root:

```bash
pip install -r requirements.txt
python -m solution.ingestion.run_pipeline
python -m pytest -v
```

The application requires `AGENTIC_FERNET_KEY` and `AGENTIC_HASH_KEY` environment variables to be configured before running.

## Design

The solution uses a modular Python architecture.

- `processing`: Normalizes phone numbers and validates incoming records.
- `ingestion`: Reads CSV batches, maps fields using schemas, rejects invalid records, and merges duplicate customers.
- `database`: Stores customer data in SQLite. Customer names and phone numbers are encrypted, and phone numbers are matched using keyed HMAC hashes.
- `events`: Reads JSONL interaction events, detects duplicate event IDs, stores events, and links them to customer leads.
- `reporting`: Generates batch summaries, daily overviews, lead reports, rejection reports, and a data quality report.

The customer table uses a unique constraint on workflow ID and phone hash. The event ledger uses event IDs as primary keys and database triggers to prevent updates and deletions.

## Decisions and assumptions

| Decision | Why | Alternative considered |
|---|---|---|
| SQLite database | Simple persistent relational storage | PostgreSQL |
| HMAC-SHA256 for phone matching | Supports matching without storing plain phone numbers as identifiers | Plain-text phone matching |
| Fernet encryption for PII | Protects customer names and phone numbers | Plain-text storage |
| Schema-based validation | Handles different CSV header formats consistently | Hard-coded column positions |
| Event ID as primary key | Prevents duplicate event insertion | Duplicate checks only in Python |

## Failure modes considered

- Invalid CSV records are rejected with reasons.
- Malformed JSONL events are counted and skipped.
- Duplicate lead records are merged using workflow and phone identity.
- Duplicate event IDs are ignored by the database.
- Events without a matching customer are marked as orphans and retried.
- Encryption and hashing keys are loaded from environment variables.
- Database errors trigger transaction rollback.

Known limitation: Orphan events may remain when no matching customer record exists.

## Testing

- Tested phone normalization, including invalid and empty phone numbers.
- Tested header mapping and required-field validation.
- Tested date, decimal, and language validation.
- Ran the test suite using `python -m pytest -v`.

**Result: 15 tests passed.**

The full ingestion pipeline was also executed, and all five reports were generated.

## Results

- Total lead rows processed: 2,057
- Rejected lead rows: 108
- Unique customers saved: 1,892
- Duplicate lead rows merged: 57
- Total interaction events processed: 8,745
- Malformed events: 8
- Duplicate events detected: 199
- Orphan events remaining after retry: 464

Note: The event database already contained records from earlier pipeline runs, so the already-stored event count reflects reruns.

Generated reports are available in the `reports/` folder.

## If I had another day

- Add more automated tests for database and event processing.
- Improve event-to-lead matching for orphan events.
- Add integration tests for the complete pipeline.
- Improve logging and error reporting.
- Test the solution from a completely clean database.
