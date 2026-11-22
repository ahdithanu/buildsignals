"""Pluggable email-sending abstraction.

We deliberately keep the surface tiny — one `send()` call with html+text —
so swapping providers (Resend → SES → Postmark) only touches this module.

Provider choice is fixed at import. Deployed environments require a Resend
key and explicit sender; missing configuration disables recovery, not the API.
Local console transport never logs addresses, message bodies or reset tokens.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

from app.config import IS_DEPLOYED

logger = logging.getLogger(__name__)


class EmailService(Protocol):
    available: bool

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        ...


class EmailDeliveryUnavailable(RuntimeError):
    pass


class UnavailableEmailService:
    available = False

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        raise EmailDeliveryUnavailable("Email delivery is not configured")


class ConsoleEmailService:
    """No-op local sender; tests replace send() to capture outgoing messages.

    Metadata-only logging also keeps local reset credentials out of terminals.
    """

    available = True

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        logger.info("email_delivery_skipped: local console transport")


class ResendEmailService:
    """Resend-backed sender.

    Constructed lazily — we only import `resend` when the env var is set,
    so the package is a soft dependency for local dev.
    """

    available = True

    def __init__(self) -> None:
        import resend  # type: ignore

        resend.api_key = os.environ["RESEND_API_KEY"]
        resend.default_http_client = resend.RequestsClient(timeout=5)
        self._resend = resend
        self._from = os.environ.get(
            "RESEND_FROM_ADDRESS",
            "BuildSignals <noreply@dealsignal.dev>",
        )

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        self._resend.Emails.send(
            {
                "from": self._from,
                "to": [to],
                "subject": subject,
                "html": html,
                "text": text,
            }
        )


def _build_service() -> EmailService:
    key = os.environ.get("RESEND_API_KEY", "").strip()
    sender = os.environ.get("RESEND_FROM_ADDRESS", "").strip()
    if IS_DEPLOYED and (not key or not sender):
        logger.warning("email_delivery_unavailable: provider configuration incomplete")
        return UnavailableEmailService()
    if key:
        return ResendEmailService()
    return ConsoleEmailService()


# Module-level singleton. Tests swap `.send` via monkeypatch.setattr.
email_service: EmailService = _build_service()


def email_delivery_available() -> bool:
    """Account-independent transport configuration check; sends no email."""
    return email_service.available


def get_email_service() -> EmailService:
    """Return the process-wide email service singleton."""
    return email_service
