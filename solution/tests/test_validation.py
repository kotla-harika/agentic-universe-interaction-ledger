
from solution.processing.validation import (
    normalize_header,
    build_header_mapping,
    check_required_fields,
    normalize_field_value,
    validate_record
)



def test_normalize_header():
    assert normalize_header("Customer_Name") == "customer name"
    assert normalize_header(" CUSTOMER NAME ") == "customer name"


def test_header_mapping():
    schema = {
        "fields": [
            {
                "name": "customer_name",
                "aliases": ["name", "insured name"]
            }
        ]
    }

    mapping = build_header_mapping(schema)

    assert mapping["customer name"] == "customer_name"
    assert mapping["insured name"] == "customer_name"


def test_missing_required_field():
    schema = {
        "fields": [
            {"name": "customer_name", "required": True},
            {"name": "phone", "required": True}
        ]
    }

    record = {
        "customer_name": "Ravi",
        "phone": ""
    }

    result = check_required_fields(record, schema)

    assert result == "missing required:phone"


def test_valid_record():
    schema = {
        "fields": [
            {"name": "customer_name", "required": True},
            {"name": "phone", "required": True}
        ]
    }

    record = {
        "customer_name": "Ravi",
        "phone": "9876543210"
    }

    assert check_required_fields(record, schema) is None

def test_valid_date():
    field = {"name": "policy_expiry", "type": "date"}

    result, valid = normalize_field_value(
        "01-Dec-2026", field
    )

    assert valid is True
    assert result == "2026-12-01"


def test_invalid_date():
    field = {"name": "policy_expiry", "type": "date"}

    result, valid = normalize_field_value(
        "31/02/2026", field
    )

    assert valid is False
    assert result is None


def test_decimal_amount():
    field = {"name": "premium_amount", "type": "decimal"}

    result, valid = normalize_field_value(
        "₹5,000", field
    )

    assert valid is True
    assert result == "5000.00"


def test_invalid_decimal():
    field = {"name": "premium_amount", "type": "decimal"}

    result, valid = normalize_field_value(
        "-500", field
    )

    assert valid is False


def test_valid_language():
    field = {
        "name": "preferred_language",
        "type": "enum",
        "values": ["en", "hi", "ta", "te", "kn", "mr"]
    }

    result, valid = normalize_field_value("TE", field)

    assert valid is True
    assert result == "te"


def test_invalid_language():
    field = {
        "name": "preferred_language",
        "type": "enum",
        "values": ["en", "hi", "ta", "te", "kn", "mr"]
    }

    result, valid = normalize_field_value("French", field)

    assert valid is False
