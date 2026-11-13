import csv
import json
import sqlite3

from pathlib import Path
from solution.database.database import decrypt_value


# Find the main project folder
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Database location
DB_PATH = PROJECT_ROOT / "agentic_universe.db"

# Assignment A schema and disposition files
SCHEMA_DIR = PROJECT_ROOT / "assignment-a-data" / "schemas"

DISPOSITIONS_FILE = SCHEMA_DIR / "dispositions.csv"


def get_connection():
    """Connect to the SQLite database."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def create_output_folder(output_dir):
    """Create the reports folder if it does not exist."""
    output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    return output_path
def load_dispositions():
    """Load disposition definitions from dispositions.csv."""

    dispositions = {}

    with open(DISPOSITIONS_FILE, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            workflow_id = row["workflow_id"]
            code = row["code"]

            dispositions[(workflow_id, code)] = {
                "label": row["label"],
                "is_terminal": row["is_terminal"].strip().lower() == "true",
                "is_success": row["is_success"].strip().lower() == "true"
            }

    return dispositions


def load_workflow_schemas():
    """Load both workflow schemas."""

    schemas = {}

    for workflow_id in ("motor_renewal", "policy_feedback"):
        schema_path = SCHEMA_DIR / f"{workflow_id}.json"

        with open(schema_path, "r", encoding="utf-8") as file:
            schemas[workflow_id] = json.load(file)

    return schemas
def load_database_data():
    """Load saved leads, events, and their links from SQLite."""

    connection = get_connection()

    try:
        # Load customer leads
        lead_rows = connection.execute("""
            SELECT
                lead_id,
                workflow_id,
                phone_hash,
                phone_enc,
                batch_id,
                other_data
            FROM leads
        """).fetchall()

        # Load events and their current lead links
        event_rows = connection.execute("""
            SELECT
                e.event_id,
                e.event_type,
                e.workflow_id,
                e.call_id,
                e.occurred_at,
                e.payload_json,
                el.lead_id,
                el.link_status
            FROM interaction_events e
            LEFT JOIN event_lead_links el
                ON e.event_id = el.event_id
        """).fetchall()

        leads = [dict(row) for row in lead_rows]
        events = []

        for row in event_rows:
            event = dict(row)

            try:
                event["payload"] = json.loads(
                    event.pop("payload_json") or "{}"
                )
            except json.JSONDecodeError:
                event["payload"] = {}

            events.append(event)

        return leads, events

    finally:
        connection.close()
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def parse_event_time(value):
    """Convert event timestamps into IST."""

    if not value:
        return None

    value = value.strip().replace("Z", "+00:00")

    try:
        event_time = datetime.fromisoformat(value)

        # Naive timestamps are already in IST
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=IST)

        return event_time.astimezone(IST)

    except ValueError:
        return None


def get_disposition_code(event):
    """Extract the disposition code from an event payload."""

    payload = event.get("payload") or {}

    return (
        payload.get("disposition_code")
        or payload.get("code")
    )


def get_effective_disposition(call_events):
    """
    Return the latest override if present.
    Otherwise return the latest disposition.set.
    """

    overrides = [
        event for event in call_events
        if event["event_type"] == "disposition.override"
    ]

    if overrides:
        latest = max(
            overrides,
            key=lambda event: parse_event_time(event["occurred_at"])
            or datetime.min.replace(tzinfo=IST)
        )
        return get_disposition_code(latest)

    dispositions = [
        event for event in call_events
        if event["event_type"] == "disposition.set"
    ]

    if dispositions:
        latest = max(
            dispositions,
            key=lambda event: parse_event_time(event["occurred_at"])
            or datetime.min.replace(tzinfo=IST)
        )
        return get_disposition_code(latest)

    return None    
def build_call_records(events, dispositions):
    """Group linked events into calls and calculate call details."""

    grouped_calls = {}

    for event in events:
        call_id = event.get("call_id")

        if not call_id:
            continue

        key = (event["workflow_id"], call_id)

        grouped_calls.setdefault(key, []).append(event)

    calls = []
    unknown_disposition_events = 0

    for (workflow_id, call_id), call_events in grouped_calls.items():

        initiated_events = [
            event for event in call_events
            if event["event_type"] == "call.initiated"
            and event["link_status"] == "linked"
        ]

        # A call counts only when its initiated event is linked.
        if not initiated_events:
            continue

        initiated = min(
            initiated_events,
            key=lambda event: parse_event_time(event["occurred_at"])
            or datetime.max.replace(tzinfo=IST)
        )

        initiated_time = parse_event_time(initiated["occurred_at"])

        connected = any(
            event["event_type"] == "call.connected"
            for event in call_events
        )

        telephony_failed = any(
            event["event_type"] == "call.telephony_failed"
            for event in call_events
        )

        disposition_events = [
            event for event in call_events
            if event["event_type"] in (
                "disposition.set",
                "disposition.override"
            )
        ]

        for event in disposition_events:
            code = get_disposition_code(event)

            if code and (workflow_id, code) not in dispositions:
                unknown_disposition_events += 1

        effective_code = get_effective_disposition(call_events)

        disposition_info = dispositions.get(
            (workflow_id, effective_code)
        )

        # Ignore unknown disposition codes.
        if effective_code and disposition_info is None:
            effective_code = None

        calls.append({
            "workflow_id": workflow_id,
            "call_id": call_id,
            "lead_id": initiated["lead_id"],
            "date": initiated_time.date().isoformat()
                if initiated_time else None,
            "initiated_at": initiated_time,
            "connected": connected,
            "telephony_failed": telephony_failed,
            "disposition": effective_code,
            "is_terminal": (
                disposition_info["is_terminal"]
                if disposition_info else False
            ),
            "is_success": (
                disposition_info["is_success"]
                if disposition_info else False
            )
        })

    return calls, unknown_disposition_events    
def calculate_lead_buckets(leads, calls):
    """Calculate the final bucket for every lead."""

    calls_by_lead = {}

    for call in calls:
        lead_id = call["lead_id"]

        if lead_id is not None:
            calls_by_lead.setdefault(lead_id, []).append(call)

    lead_results = []

    for lead in leads:
        lead_calls = calls_by_lead.get(lead["lead_id"], [])

        if not lead_calls:
            bucket = "yet_to_reach_out"

        elif any(call["is_terminal"] for call in lead_calls):
            bucket = "completed"

        elif all(call["telephony_failed"] for call in lead_calls):
            bucket = "in_progress_telephony_failed"

        else:
            bucket = "in_progress_dialed"

        lead_results.append({
            "lead": lead,
            "calls": lead_calls,
            "bucket": bucket
        })

    return lead_results
def write_csv(output_path, filename, headers, rows):
    """Write a CSV report with the required column order."""

    file_path = output_path / filename

    with open(file_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=headers,
            lineterminator="\n"
        )

        writer.writeheader()
        writer.writerows(rows)

    return file_path


def generate_batch_summary(lead_results, output_path):
    """Generate batch_summary.csv."""

    summary = {}

    for result in lead_results:
        lead = result["lead"]

        key = (lead["workflow_id"], lead["batch_id"])

        if key not in summary:
            summary[key] = {
                "workflow_id": lead["workflow_id"],
                "batch_id": lead["batch_id"],
                "total_leads": 0,
                "yet_to_reach_out": 0,
                "in_progress_telephony_failed": 0,
                "in_progress_dialed": 0,
                "completed": 0
            }

        summary[key]["total_leads"] += 1
        summary[key][result["bucket"]] += 1

    rows = sorted(
        summary.values(),
        key=lambda row: (row["workflow_id"], row["batch_id"])
    )

    headers = [
        "workflow_id",
        "batch_id",
        "total_leads",
        "yet_to_reach_out",
        "in_progress_telephony_failed",
        "in_progress_dialed",
        "completed"
    ]

    return write_csv(
        output_path,
        "batch_summary.csv",
        headers,
        rows
    )
def generate_daily_overview(calls, output_path):
    """Generate daily_overview.csv."""

    daily_data = {}

    for call in calls:
        if not call["date"]:
            continue

        key = (call["workflow_id"], call["date"])

        if key not in daily_data:
            daily_data[key] = {
                "workflow_id": call["workflow_id"],
                "date": call["date"],
                "total_calls": 0,
                "connected_calls": 0,
                "success_leads": set()
            }

        daily_data[key]["total_calls"] += 1

        if call["connected"]:
            daily_data[key]["connected_calls"] += 1

        if call["is_success"] and call["lead_id"] is not None:
            daily_data[key]["success_leads"].add(call["lead_id"])

    rows = []

    for key in sorted(daily_data):
        item = daily_data[key]

        total_calls = item["total_calls"]
        connected_calls = item["connected_calls"]

        connectivity_rate = connected_calls / total_calls

        rows.append({
            "workflow_id": item["workflow_id"],
            "date": item["date"],
            "total_calls": total_calls,
            "connected_calls": connected_calls,
            "connectivity_rate": f"{connectivity_rate:.4f}",
            "success_leads": len(item["success_leads"])
        })

    headers = [
        "workflow_id",
        "date",
        "total_calls",
        "connected_calls",
        "connectivity_rate",
        "success_leads"
    ]

    return write_csv(
        output_path,
        "daily_overview.csv",
        headers,
        rows
    )

def generate_lead_report(lead_results, output_path):
    """Generate lead_report.csv with one row per lead."""

    rows = []

    for result in lead_results:
        lead = result["lead"]
        calls = result["calls"]

        other_data = json.loads(lead["other_data"] or "{}")

        if lead["workflow_id"] == "motor_renewal":
            external_ref = other_data.get("policy_number", "")
        else:
            external_ref = other_data.get("order_id", "")

        phone = str(decrypt_value(lead["phone_enc"]))
        phone_masked = "+91*******" + phone[-4:]

        valid_calls = [
            call for call in calls
            if call["initiated_at"] is not None
        ]

        latest_call = None

        if valid_calls:
            latest_call = max(
                valid_calls,
                key=lambda call: call["initiated_at"]
            )

        if latest_call:
            last_call_at = latest_call["initiated_at"].isoformat()
            current_disposition = latest_call["disposition"] or ""
        else:
            last_call_at = ""
            current_disposition = ""

        rows.append({
            "workflow_id": lead["workflow_id"],
            "external_ref": external_ref,
            "batch_id": lead["batch_id"],
            "phone_masked": phone_masked,
            "bucket": result["bucket"],
            "total_calls": len(calls),
            "connected_calls": sum(
                1 for call in calls if call["connected"]
            ),
            "last_call_at": last_call_at,
            "current_disposition": current_disposition,
            "ever_success": any(
                call["is_success"] for call in calls
            )
        })

    rows.sort(
        key=lambda row: (
            row["workflow_id"],
            row["external_ref"]
        )
    )

    headers = [
        "workflow_id",
        "external_ref",
        "batch_id",
        "phone_masked",
        "bucket",
        "total_calls",
        "connected_calls",
        "last_call_at",
        "current_disposition",
        "ever_success"
    ]

    return write_csv(
        output_path,
        "lead_report.csv",
        headers,
        rows
    )
def generate_rejections_report(rejected_rows, output_path):
    """Generate rejections.csv without storing customer PII."""

    rows = []

    for item in rejected_rows:
        rows.append({
            "workflow_id": item["workflow_id"],
            "batch_id": item["batch_id"],
            "row_number": item["row_number"],
            "reason": item["reason"]
        })

    rows.sort(
        key=lambda row: (
            row["workflow_id"],
            row["batch_id"],
            row["row_number"]
        )
    )

    headers = [
        "workflow_id",
        "batch_id",
        "row_number",
        "reason"
    ]

    return write_csv(
        output_path,
        "rejections.csv",
        headers,
        rows
    )