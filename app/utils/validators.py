"""Reusable validation helpers."""

import re


def is_valid_email(email: str) -> bool:
    """Basic email format validation."""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email))


def is_valid_phone(phone: str) -> bool:
    """Accept digits, spaces, dashes, parens, plus sign. At least 7 digits."""
    digits = re.sub(r"\D", "", phone)
    return 7 <= len(digits) <= 15


def is_valid_zip_code(zip_code: str) -> bool:
    """US zip: 5 digits or 5+4."""
    return bool(re.match(r"^\d{5}(-\d{4})?$", zip_code))


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp a numeric value between lo and hi."""
    return max(lo, min(hi, value))


def is_valid_uuid(value: str) -> bool:
    """Check if string looks like a UUID v4."""
    pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    return bool(re.match(pattern, value, re.IGNORECASE))
