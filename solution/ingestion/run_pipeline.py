from solution.database.database import create_tables, save_leads
from solution.ingestion.lead_ingestion import process_csv_batch
from solution.events.event_ingestion import ingest_event_file
from solution.reporting.report_generator import (
    create_output_folder,
    load_dispositions,
    load_database_data,
    build_call_records,
    calculate_lead_buckets,
    generate_batch_summary,
    generate_daily_overview,
    generate_lead_report,
    generate_rejections_report
)

# Store all unique customers
lead_store = {}

batches = [
    (
        "data/drop_1/leads/motor_renewal/batch_001.csv",
        "assignment-a-data/schemas/motor_renewal.json",
        "motor_renewal",
        "batch_001"
    ),
    (
        "data/drop_1/leads/motor_renewal/batch_002.csv",
        "assignment-a-data/schemas/motor_renewal.json",
        "motor_renewal",
        "batch_002"
    ),
    (
        "data/drop_1/leads/policy_feedback/batch_001.csv",
        "assignment-a-data/schemas/policy_feedback.json",
        "policy_feedback",
        "batch_001"
    ),
    (
        "data/drop_1/leads/policy_feedback/batch_002.csv",
        "assignment-a-data/schemas/policy_feedback.json",
        "policy_feedback",
        "batch_002"
    ),
    (
        "data/drop_2/leads/motor_renewal/batch_003.csv",
        "assignment-a-data/schemas/motor_renewal.json",
        "motor_renewal",
        "batch_003"
    ),
    (
        "data/drop_2/leads/policy_feedback/batch_003.csv",
        "assignment-a-data/schemas/policy_feedback.json",
        "policy_feedback",
        "batch_003"
    )
]
batch_results = []
all_rejected_rows = []

for csv_path, schema_path, workflow, batch in batches:

    result = process_csv_batch(
        csv_path,
        schema_path,
        workflow,
        batch,
        lead_store
    )
    batch_results.append({
             "workflow_id": workflow,
             "batch_id": batch,
        **result
    })

    all_rejected_rows.extend(result["rejected_rows"])

    print("\nPROCESSING:", workflow, batch)
    print("RESULT:", result)
# Apply schema defaults after all batches are merged
import json

schema_paths = {
    "motor_renewal": "assignment-a-data/schemas/motor_renewal.json",
    "policy_feedback": "assignment-a-data/schemas/policy_feedback.json"
}

schemas = {}

for workflow, schema_path in schema_paths.items():
    with open(schema_path, "r", encoding="utf-8") as file:
        schemas[workflow] = json.load(file)

for lead in lead_store.values():
    workflow = lead["workflow_id"]
    schema = schemas[workflow]

    for field in schema["fields"]:
        field_name = field["name"]

        if lead.get(field_name) is None and "default" in field:
            lead[field_name] = field["default"]    

print("\n========== FINAL SUMMARY ==========")
print("TOTAL UNIQUE CUSTOMERS:", len(lead_store))

# Save customers into SQLite database
create_tables()
save_leads(lead_store)

print("TOTAL CUSTOMERS SAVED:", len(lead_store))

# Process customer interaction events
event_files = [
    "data/drop_1/events/events_0001.jsonl",
    "data/drop_2/events/events_1001.jsonl"
]

print("\n========== EVENT PROCESSING ==========")

total_events = 0
total_malformed = 0
total_duplicates = 0
total_orphans = 0
total_already_stored = 0

for event_file in event_files:

    print("\nPROCESSING EVENT FILE:", event_file)

    result = ingest_event_file(event_file, lead_store)

    print("RESULT:", result)

    total_events += result["events_total"]
    total_malformed += result["malformed_events"]
    total_duplicates += result["duplicate_events"]
    total_orphans += result["orphan_events"]
    total_already_stored += result["already_stored_events"]

print("\n========== EVENT SUMMARY ==========")
print("TOTAL EVENTS:", total_events)
print("MALFORMED EVENTS:", total_malformed)
print("DUPLICATE EVENTS:", total_duplicates)
print("ORPHAN EVENTS:", total_orphans)
print("ALREADY STORED EVENTS:", total_already_stored)
# Generate all required reports
from collections import Counter

print("\n========== GENERATING REPORTS ==========")

# Create reports folder
output_dir = create_output_folder("reports")

# Load saved database records
leads, events = load_database_data()

# Load dispositions and build call records
dispositions = load_dispositions()
calls, unknown_disposition_events = build_call_records(
    events, dispositions
)

# Calculate final lead buckets
lead_results = calculate_lead_buckets(leads, calls)

# Generate four CSV reports
generate_batch_summary(lead_results, output_dir)
generate_daily_overview(calls, output_dir)
generate_lead_report(lead_results, output_dir)
generate_rejections_report(all_rejected_rows, output_dir)

# Calculate rejection reasons
rejection_counts = Counter(
    item["reason"] for item in all_rejected_rows
)

# Create data quality report
data_quality = {
    "lead_rows_total": sum(
        item["total_rows"] for item in batch_results
    ),
    "lead_rows_rejected": sum(
        item["rejected_records"] for item in batch_results
    ),
    "rejections_by_reason": dict(rejection_counts),
    "duplicate_lead_rows_merged": sum(
        item["merged_duplicates"] for item in batch_results
    ),
    "field_warnings": sum(
        item["field_warnings"] for item in batch_results
    ),
    "events_total": total_events,
    "malformed_events": total_malformed,
    "duplicate_events_dropped": total_duplicates,
    "orphan_events": total_orphans,
    "unknown_disposition_events": unknown_disposition_events
}

# Save data_quality.json
with open(output_dir / "data_quality.json", "w", encoding="utf-8") as file:
    json.dump(data_quality, file, indent=4)

print("\nALL FIVE REPORTS GENERATED!")
print("Reports saved in:", output_dir)