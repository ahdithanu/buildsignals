"""Pluggable email-sending abstraction.

We deliberately keep the surface tiny — one `send()` call with html+text —
so swapping providers (Resend → SES → Postmark) only touches this module.

Provider choice is a one-time decision at import: if `RESEND_API_KEY` is
set in the environment, we wire up the Resend SDK; otherwise we fall
back to a console logger that just prints what would have been sent. The
console fallback keeps local dev and tests working without any network
calls or API keys, and the singleton can be monkey-patched in tests to
capture outgoing mail.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailService(Protocol):
    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        ...


class ConsoleEmailService:
    """No-op sender that logs the message at INFO. Default in dev/tests.

    Tests monkey-patch `.send` directly on the singleton to capture calls,
    so the body of this method is only what shows up in dev terminals.
    """

    def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        logger.info("[email] to=%s subject=%s\n%s\n", to, subject, text)


class ResendEmailService:
    """Resend-backed sender.

    Constructed lazily — we only import `resend` when the env var is set,
    so the package is a soft dependency for local dev.
    """

    def __init__(self) -> None:
        import resend  # type: ignore

        resend.api_key = os.environ["RESEND_API_KEY"]
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
    if os.environ.get("RESEND_API_KEY"):
        return ResendEmailService()
    return ConsoleEmailService()


# Module-level singleton. Tests swap `.send` via monkeypatch.setattr.
email_service: EmailService = _build_service()


def get_email_service() -> EmailService:
    """Return the process-wide email service singleton."""
    return email_service
