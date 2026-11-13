
import csv

from solution.processing.validation import (
    build_header_mapping,
    normalize_header,
    validate_record
)


def read_csv_file(file_path):
    """
    Read a CSV file and return its headers and rows.
    """

    with open(
        file_path,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        headers = reader.fieldnames
        rows = list(reader)

    return headers, rows


def map_csv_record(row, schema):
    """
    Convert original CSV column names
    into standard schema field names.
    """

    header_mapping = build_header_mapping(schema)

    record = {
        field["name"]: None
        for field in schema["fields"]
    }

    for original_header, value in row.items():

        standard_header = normalize_header(original_header)

        field_name = header_mapping.get(standard_header)

        if field_name is not None:
            record[field_name] = value

    return record

def ingest_csv_file(csv_path, schema):
    """
    Read, map and validate every customer
    in one CSV file.
    """

    headers, rows = read_csv_file(csv_path)

    valid_records = []
    rejected_records = []

    total_rows = 0
    field_warnings = 0

    for row in rows:

        # Ignore completely blank rows
        if not any(
            str(value or "").strip()
            for value in row.values()
        ):
            continue

        total_rows += 1

        # Convert original headers into standard fields
        record = map_csv_record(row, schema)

        # Validate customer information
        normalized, reason, warnings = validate_record(
            record, schema
        )

        field_warnings += warnings

        if reason:
            rejected_records.append({
                "row_number": total_rows,
                "reason": reason
            })
        else:
            valid_records.append(normalized)

    return {
        "total_rows": total_rows,
        "valid_records": valid_records,
        "rejected_records": rejected_records,
        "field_warnings": field_warnings
    }

def merge_valid_records(lead_store, valid_records, workflow_id, batch_id):
    """
    Identify duplicate customers and merge their records.

    Customer identity:
    workflow_id + normalized phone number.

    The first valid record creates the lead.
    Later non-empty values overwrite existing values.
    The original batch_id is preserved.
    """

    merged_duplicates = 0

    for record in valid_records:

        phone = record.get("phone")

        if not phone:
            continue

        # Create a unique customer identity
        identity = (workflow_id, phone)

        # First valid record creates the customer
        if identity not in lead_store:

            new_lead = record.copy()

            new_lead["workflow_id"] = workflow_id
            new_lead["batch_id"] = batch_id

            lead_store[identity] = new_lead

        else:
            # Customer already exists
            existing_lead = lead_store[identity]

            merged_duplicates += 1

            # Update only non-empty values
            for field, value in record.items():

                if value is not None and str(value).strip() != "":
                    existing_lead[field] = value

    return merged_duplicates


def process_csv_batch(csv_path, schema_path, workflow_id, batch_id, lead_store):

    import json

    with open(schema_path, "r", encoding="utf-8") as file:
        schema = json.load(file)

    result = ingest_csv_file(csv_path, schema)
    for rejected in result["rejected_records"]:
        rejected["workflow_id"] = workflow_id
        rejected["batch_id"] = batch_id

    merged = merge_valid_records(
        lead_store,
        result["valid_records"],
        workflow_id,
        batch_id
    )

    return {
        "total_rows": result["total_rows"],
        "valid_records": len(result["valid_records"]),
        "rejected_records": len(result["rejected_records"]),
        "rejected_rows": result["rejected_records"],
        "field_warnings": result["field_warnings"],
        "merged_duplicates": merged
    }

