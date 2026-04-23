"""Server-side password strength checks for /auth/register.

These run *in addition* to the pydantic min-length 8 on RegisterRequest.
The schema check rejects obvious garbage fast; this module rejects the
sneakier failure modes — passwords that are long but still trivially
guessable (all-digits, contains the user's email handle, etc.).

We intentionally avoid a huge common-passwords dictionary here; the
value-per-KB is poor for a pilot and Argon2/bcrypt makes offline
cracking of strong-ish passwords impractical anyway.
"""
from __future__ import annotations

from typing import Optional

MIN_LENGTH = 12
MAX_LENGTH = 128

# A short list of the passwords that show up in every breach dump. This
# is not a substitute for a real dictionary — it's a last-line guardrail
# against someone typing "password1234" into the pilot demo.
_OBVIOUS_BAD = {
    "password", "password1", "password123", "password1234",
    "qwerty", "qwerty123", "letmein", "letmein123",
    "welcome", "welcome1", "admin", "admin123", "administrator",
    "123456789012", "111111111111", "abcdefghijkl",
    "iloveyou", "trustno1", "dragon123",
}


class PasswordPolicyError(ValueError):
    """Raised when a candidate password fails policy."""


def _contains_email_handle(password: str, email: Optional[str]) -> bool:
    if not email:
        return False
    handle = email.split("@", 1)[0].lower()
    # Only flag substrings of length ≥ 4 — "bob" inside "bobsleigh2024"
    # is fine, but "bob.smith" showing up verbatim is not.
    return len(handle) >= 4 and handle in password.lower()


def validate_password(password: str, *, email: Optional[str] = None) -> None:
    """Raise PasswordPolicyError on weak passwords. Returns None on success.

    Order is from cheapest to most specific — we want the first failure the
    user fixes to also reveal the *next* reason they'd fail, not the same one.
    """
    if len(password) < MIN_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_LENGTH} characters long"
        )
    if len(password) > MAX_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {MAX_LENGTH} characters long"
        )
    if password.isdigit():
        raise PasswordPolicyError("Password must not be only digits")
    if password.isalpha():
        raise PasswordPolicyError("Password must include at least one digit or symbol")
    if password.lower() in _OBVIOUS_BAD:
        raise PasswordPolicyError("Password is too common — pick something else")
    if _contains_email_handle(password, email):
        raise PasswordPolicyError("Password must not contain your email address")
