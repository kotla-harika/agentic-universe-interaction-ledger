
import re


def normalize_phone(phone):
    """
    Normalize Indian mobile numbers.

    Returns:
        Standard phone number (+91XXXXXXXXXX)
        or None if the number is invalid.
    """

    # Check missing values
    if phone is None:
        return None

    # Convert to string and remove surrounding spaces
    phone = str(phone).strip()

    if not phone:
        return None

    # Keep only digits
    digits = re.sub(r"\D", "", phone)

    # Remove Indian country code
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]

    # Remove leading zero
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    # Validate mobile number
    if len(digits) != 10:
        return None

    if digits[0] not in "6789":
        return None

    # Return standardized number
    return "+91" + digits
