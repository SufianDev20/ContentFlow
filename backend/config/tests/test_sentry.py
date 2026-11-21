from unittest.mock import patch

from config.sentry import configure_sentry


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
