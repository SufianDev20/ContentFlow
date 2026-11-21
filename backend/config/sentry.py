"""Sentry setup, kept out of settings.py so it can be unit-tested."""

import logging
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration


def configure_sentry(dsn: str, traces_sample_rate: float, send_default_pii: bool) -> bool:
    """Initialize Sentry only when a DSN is configured; returns whether it was."""
    if not dsn:
        return False
    sentry_logging = LoggingIntegration(
        level=logging.INFO,  # Capture INFO and above as breadcrumbs
        event_level=logging.ERROR,  # Send ERROR and CRITICAL logs as Sentry events
    )
    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration(), sentry_logging],
        send_default_pii=send_default_pii,
        enable_logs=True,
        traces_sample_rate=traces_sample_rate,
    )
    return True
