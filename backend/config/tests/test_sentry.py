from unittest.mock import patch
from django.test import SimpleTestCase
from config.sentry import configure_sentry


class ConfigureSentryTests(SimpleTestCase):
    @patch("config.sentry.sentry_sdk.init")
    def test_does_not_initialize_when_dsn_is_empty(self, mock_init):
        result = configure_sentry(
            dsn="", traces_sample_rate=0.1, send_default_pii=False
        )
        self.assertFalse(result)
        mock_init.assert_not_called()

    @patch("config.sentry.sentry_sdk.init")
    def test_initializes_when_dsn_is_set(self, mock_init):
        result = configure_sentry(
            dsn="https://example@sentry.io/1", traces_sample_rate=0.2, send_default_pii=True
        )
        self.assertTrue(result)
        mock_init.assert_called_once()

    @patch("config.sentry.sentry_sdk.init")
    def test_passes_traces_sample_rate_and_pii_flag_through(self, mock_init):
        configure_sentry(
            dsn="https://example@sentry.io/1", traces_sample_rate=0.35, send_default_pii=True
        )
        _, kwargs = mock_init.call_args
        self.assertEqual(kwargs["traces_sample_rate"], 0.35)
        self.assertTrue(kwargs["send_default_pii"])

    @patch("config.sentry.sentry_sdk.init")
    def test_defaults_send_default_pii_false_is_passed_through(self, mock_init):
        configure_sentry(
            dsn="https://example@sentry.io/1", traces_sample_rate=0.1, send_default_pii=False
        )
        _, kwargs = mock_init.call_args
        self.assertFalse(kwargs["send_default_pii"])
