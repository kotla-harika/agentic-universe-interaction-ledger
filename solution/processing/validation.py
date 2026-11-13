
import re


def normalize_header(header):
    """
    Normalize CSV column names.

    Example:
    'Customer_Name' -> 'customer name'
    ' CUSTOMER NAME ' -> 'customer name'
    """

    header = str(header).strip().lower()

    # Replace hyphens and whitespace with one space
    header = re.sub(r"[_\s]+", " ", header)

    return header


def build_header_mapping(schema):
    """
    Create a dictionary connecting CSV headers
    to the official schema field names.
    """

    mapping = {}

    for field in schema["fields"]:

        field_name = field["name"]

        # Include official field name
        mapping[normalize_header(field_name)] = field_name

        # Include alternative column names
        for alias in field.get("aliases", []):
            mapping[normalize_header(alias)] = field_name

    return mapping


def check_required_fields(record, schema):
    """
    Find the first missing required field.

    Returns rejection reason or None.
    """

    for field in schema["fields"]:

        if field.get("required", False):

            field_name = field["name"]

            value = record.get(field_name)

            if value is None or str(value).strip() == "":
                return f"missing required:{field_name}"

    return None  

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from solution.processing.normalization import normalize_phone


def normalize_field_value(value, field):
    """
    Normalize and validate one field according to its schema.

    Returns:
        (normalized_value, is_valid)
    """

    if value is None or str(value).strip() == "":
        return None, True

    value = str(value).strip()
    field_type = field["type"]

    # String validation
    if field_type == "string":
        return value, True

    # Phone validation
    if field_type == "phone":
        result = normalize_phone(value)

        if result is None:
            return None, False

        return result, True

    # Date validation
    if field_type == "date":
        formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d-%b-%Y"
        ]

        for date_format in formats:
            try:
                result = datetime.strptime(
                    value, date_format
                )
                return result.date().isoformat(), True
            except ValueError:
                continue

        return None, False

    # Decimal validation
    if field_type == "decimal":
        cleaned = value

        for prefix in ["₹", "Rs.", "Rs", "INR"]:
            if cleaned.upper().startswith(prefix.upper()):
                cleaned = cleaned[len(prefix):].strip()
                break

        cleaned = cleaned.replace(",", "")

        try:
            amount = Decimal(cleaned)

            if not amount.is_finite() or amount < 0:
                return None, False

            amount = amount.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP
            )

            return str(amount), True

        except InvalidOperation:
            return None, False

    # Enum validation
    if field_type == "enum":
        normalized = value.lower()

        allowed_values = [
            item.lower()
            for item in field.get("values", [])
        ]

        if normalized not in allowed_values:
            return None, False

        return normalized, True

    return None, False


def validate_record(record, schema):
    """
    Validate a canonical customer record.

    Returns:
        normalized_record, rejection_reason, field_warnings
    """

    normalized_record = {}
    field_warnings = 0

    for field in schema["fields"]:

        field_name = field["name"]
        value = record.get(field_name)

        # Check required fields in schema order
        if value is None or str(value).strip() == "":
            normalized_record[field_name] = None

            if field.get("required", False):
                return (
                    normalized_record,
                    f"missing required:{field_name}",
                    field_warnings
                )

            continue

        normalized_value, is_valid = normalize_field_value(
            value, field
        )

        normalized_record[field_name] = normalized_value

        if not is_valid:

            # Invalid required phone has a special reason
            if field_name == "phone":
                return (
                    normalized_record,
                    "invalid_phone",
                    field_warnings
                )

            # Invalid optional values become null
            normalized_record[field_name] = None
            field_warnings += 1

    
    return normalized_record, None, field_warnings

