
import json
from solution.processing.normalization import normalize_phone
from solution.database.database import save_event, link_event_to_lead


def read_event_file(file_path):
    """
    Read JSONL events.
    Count every non-empty line, including malformed lines.
    """

    events = []
    events_total = 0
    malformed_events = 0

    with open(file_path, "r", encoding="utf-8") as file:

        for line in file:

            if not line.strip():
                continue

            events_total += 1

            try:
                event = json.loads(line)

                if not isinstance(event, dict) or not event.get("event_id"):
                    malformed_events += 1
                    continue

                events.append(event)

            except json.JSONDecodeError:
                malformed_events += 1

    return {
        "events": events,
        "events_total": events_total,
        "malformed_events": malformed_events
    }
def process_events(events):
    """
    Remove duplicate event IDs.
    Keep the first occurrence of each event.
    """

    unique_events = []
    seen_event_ids = set()
    duplicate_events = 0

    for event in events:
        event_id = event["event_id"]

        if event_id in seen_event_ids:
            duplicate_events += 1
            continue

        seen_event_ids.add(event_id)
        unique_events.append(event)

    return {
        "events": unique_events,
        "duplicate_events": duplicate_events
    }

def link_events_to_leads(events, lead_store):
    """
    Match each event to a lead using workflow ID
    and normalized phone number.
    """

    linked_events = []
    orphan_events = []

    for event in events:

        workflow_id = event.get("workflow_id")
        phone = event.get("phone")

        normalized_phone = normalize_phone(phone) if phone else None

        if not workflow_id or not normalized_phone:
            orphan_events.append(event)
            continue

        identity = (workflow_id, normalized_phone)

        if identity in lead_store:
            linked_events.append(event)
        else:
            orphan_events.append(event)

    return {
        "linked_events": linked_events,
        "orphan_events": orphan_events
    }

def ingest_event_file(file_path, lead_store):
    """
    Read events, remove duplicates, save them,
    and link them to customer leads.
    """

    result = read_event_file(file_path)

    duplicate_result = process_events(result["events"])
    unique_events = duplicate_result["events"]

    database_duplicates = 0

    # First, save all unique events
    for event in unique_events:
        inserted = save_event(event)

        if not inserted:
            database_duplicates += 1

    # Link events after all events have been saved
    for event in unique_events:
        link_event_to_lead(event)

    # Retry links to resolve events that arrived out of order
    orphan_count = 0

    for event in unique_events:
        status = link_event_to_lead(event)

        if status == "orphan":
            orphan_count += 1

    return {
        "events_total": result["events_total"],
        "malformed_events": result["malformed_events"],
        "duplicate_events": duplicate_result["duplicate_events"],
        "already_stored_events": database_duplicates,
        "orphan_events": orphan_count
    }