"""
Sentry initialization for ContentFlow AI, extracted from settings.py so
its behavior (skip-when-no-DSN, configurable sample rate/PII) is directly
unit-testable without reloading Django settings.
"""

import logging
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration


def configure_sentry(dsn: str, traces_sample_rate: float, send_default_pii: bool) -> bool:
    """
    Initialize Sentry if, and only if, a DSN is configured.

    Args:
        dsn: Sentry DSN. Sentry is not initialized at all when this is empty
            — previously sentry_sdk.init() ran unconditionally even with an
            empty DSN, which was a silent no-op but wasted a call and risked
            confusion.
        traces_sample_rate: Fraction of transactions to trace (0.0-1.0).
            Production should use a low value (e.g. 0.1); 1.0 traces every
            request and is unnecessarily expensive at real traffic.
        send_default_pii: Whether to send request headers/IPs and other PII
            to Sentry. Defaults to False at the settings layer — an operator
            opts in explicitly per their own compliance posture.

    Returns:
        True if Sentry was initialized, False if skipped (no DSN).
    """
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
