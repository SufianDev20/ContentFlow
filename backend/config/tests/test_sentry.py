from unittest.mock import patch

import pytest
import sentry_sdk

from config.sentry import configure_sentry


@pytest.fixture
def sentry_teardown():
    yield
    sentry_sdk.init(dsn=None)  # swap the real client for a disabled one


def test_installed_sentry_sdk_accepts_our_init_options(sentry_teardown):
    # Real sentry_sdk.init, no mock: fails if the installed SDK rejects an option
    # we pass (sentry-sdk 3.0 dropped send_default_pii and broke deploys).
    started = configure_sentry(
        dsn="https://key@example.invalid/1", traces_sample_rate=0.0, send_default_pii=False
    )

    assert started is True
    assert sentry_sdk.get_client().is_active()


@patch("config.sentry.sentry_sdk.init")
def test_sentry_stays_off_without_a_dsn(init):
    assert configure_sentry(dsn="", traces_sample_rate=0.1, send_default_pii=False) is False
    init.assert_not_called()


@patch("config.sentry.sentry_sdk.init")
def test_sentry_starts_with_the_configured_dsn(init):
    started = configure_sentry(
        dsn="https://example@sentry.io/1", traces_sample_rate=0.2, send_default_pii=False
    )

    assert started is True
    assert init.call_args.kwargs["dsn"] == "https://example@sentry.io/1"
