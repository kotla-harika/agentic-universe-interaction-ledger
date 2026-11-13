
from solution.processing.normalization import normalize_phone


def test_valid_phone():
    assert normalize_phone("9876543210") == "+919876543210"


def test_country_code():
    assert normalize_phone("91-98765-43210") == "+919876543210"


def test_leading_zero():
    assert normalize_phone("09876543210") == "+919876543210"


def test_invalid_phone():
    assert normalize_phone("1234567890") is None


def test_empty_phone():
    assert normalize_phone("") is None
