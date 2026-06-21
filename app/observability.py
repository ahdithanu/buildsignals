"""Sentry initialization. Safe to import even when Sentry is disabled."""
from __future__ import annotations

import logging

from app import config

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Initialize Sentry once, at process startup. No-op when SENTRY_DSN is unset."""
    if not config.SENTRY_DSN:
        logger.info("Sentry disabled (SENTRY_DSN not set)")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning("sentry-sdk not installed — skipping Sentry init")
        return

    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.ENVIRONMENT,
        release=config.SENTRY_RELEASE,
        traces_sample_rate=config.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=config.SENTRY_PROFILES_SAMPLE_RATE,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
        send_default_pii=False,
    )
    logger.info("Sentry initialized for environment=%s", config.ENVIRONMENT)
