# AI Usage Disclosure

## Tools used

ChatGPT (OpenAI).

## What I used them for

- Understanding the assignment requirements and breaking the project into smaller tasks.
- Getting guidance on Python code for phone normalization and record validation.
- Developing CSV ingestion, database storage, encryption, and event-processing logic.
- Getting help with report generation and debugging Python errors.
- Understanding test failures and correcting implementation issues.

## What I wrote or decided myself

- Followed the project requirements and organized the implementation into separate modules.
- Selected SQLite for persistent storage.
- Used the provided workflow schemas and input datasets.
- Ran the code, checked the generated reports, and decided whether corrections were needed.
- Configured the environment variables for encryption and hashing.

## Where the AI was wrong or unhelpful

- Some suggested code had incorrect function placement or indentation.
- One suggested report-generation change caused a NameError because a variable was not defined in that function.
- I checked the traceback, shared the error, and corrected the code with assistance.

## How I verified AI-generated code

- Ran the Python test suite using `python -m pytest -v`.
- Confirmed that all 15 tests passed.
- Executed the ingestion and event-processing pipeline.
- Checked the terminal output and confirmed that all five reports were generated.
- Reviewed the generated CSV reports and database output.