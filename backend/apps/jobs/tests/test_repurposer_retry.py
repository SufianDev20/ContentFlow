"""Tests for retry/backoff behavior in apps/jobs/services/repurposer.py."""

import requests
from unittest.mock import patch, Mock, call
from django.test import SimpleTestCase, TestCase
from apps.jobs.services import repurposer
from apps.users.models import User
from apps.jobs.models import Job


def _http_error_with_status(status_code):
    """Build a real requests.exceptions.HTTPError with a populated .response,
    matching what requests.Response.raise_for_status() produces in production."""
    response = requests.models.Response()
    response.status_code = status_code
    error = requests.exceptions.HTTPError(f"{status_code} error", response=response)
    return error


class IsRetryableHttpErrorTests(SimpleTestCase):
    def test_timeout_is_retryable(self):
        self.assertTrue(
            repurposer._is_retryable_http_error(requests.exceptions.Timeout())
        )

    def test_connection_error_is_retryable(self):
        self.assertTrue(
            repurposer._is_retryable_http_error(requests.exceptions.ConnectionError())
        )

    def test_5xx_http_error_is_retryable(self):
        self.assertTrue(
            repurposer._is_retryable_http_error(_http_error_with_status(503))
        )

    def test_4xx_http_error_is_not_retryable(self):
        self.assertFalse(
            repurposer._is_retryable_http_error(_http_error_with_status(401))
        )

    def test_400_bad_request_is_not_retryable(self):
        self.assertFalse(
            repurposer._is_retryable_http_error(_http_error_with_status(400))
        )

    def test_value_error_is_not_retryable(self):
        self.assertFalse(repurposer._is_retryable_http_error(ValueError("bad shape")))

    def test_key_error_is_not_retryable(self):
        self.assertFalse(repurposer._is_retryable_http_error(KeyError("missing")))


class CallWithRetryTests(SimpleTestCase):
    @patch("apps.jobs.services.repurposer.time.sleep")
    def test_succeeds_on_first_attempt_without_sleeping(self, mock_sleep):
        fn = Mock(return_value="ok")
        result = repurposer._call_with_retry(
            fn, is_retryable=lambda exc: True, log_label="Test"
        )
        self.assertEqual(result, "ok")
        self.assertEqual(fn.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("apps.jobs.services.repurposer.time.sleep")
    def test_retries_on_retryable_error_then_succeeds(self, mock_sleep):
        fn = Mock(side_effect=[requests.exceptions.Timeout(), "ok"])
        result = repurposer._call_with_retry(
            fn, is_retryable=lambda exc: True, log_label="Test"
        )
        self.assertEqual(result, "ok")
        self.assertEqual(fn.call_count, 2)
        mock_sleep.assert_called_once_with(repurposer.RETRY_BACKOFF_SECONDS[0])

    @patch("apps.jobs.services.repurposer.time.sleep")
    def test_stops_after_max_attempts_and_raises_last_exception(self, mock_sleep):
        fn = Mock(
            side_effect=[
                requests.exceptions.Timeout("1"),
                requests.exceptions.Timeout("2"),
                requests.exceptions.Timeout("3"),
            ]
        )
        with self.assertRaises(requests.exceptions.Timeout):
            repurposer._call_with_retry(
                fn, is_retryable=lambda exc: True, log_label="Test"
            )
        self.assertEqual(fn.call_count, repurposer.RETRY_MAX_ATTEMPTS)
        self.assertEqual(
            mock_sleep.call_args_list,
            [call(repurposer.RETRY_BACKOFF_SECONDS[0]), call(repurposer.RETRY_BACKOFF_SECONDS[1])],
        )

    @patch("apps.jobs.services.repurposer.time.sleep")
    def test_does_not_retry_when_not_retryable(self, mock_sleep):
        fn = Mock(side_effect=ValueError("permanent"))
        with self.assertRaises(ValueError):
            repurposer._call_with_retry(
                fn, is_retryable=lambda exc: False, log_label="Test"
            )
        self.assertEqual(fn.call_count, 1)
        mock_sleep.assert_not_called()


class CallOpenrouterRetryTests(SimpleTestCase):
    @patch("apps.jobs.services.repurposer.time.sleep")
    @patch("apps.jobs.services.repurposer.requests.post")
    def test_retries_on_5xx_then_succeeds(self, mock_post, mock_sleep):
        failing_response = Mock()
        failing_response.raise_for_status.side_effect = _http_error_with_status(502)

        succeeding_response = Mock()
        succeeding_response.raise_for_status.return_value = None
        succeeding_response.json.return_value = {
            "choices": [{"message": {"content": "generated"}}],
            "usage": {"completion_tokens": 10, "prompt_tokens": 5},
        }

        mock_post.side_effect = [failing_response, succeeding_response]

        result = repurposer.call_openrouter("content", "openai/gpt-4o", "email")

        self.assertEqual(result["text"], "generated")
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(repurposer.RETRY_BACKOFF_SECONDS[0])

    @patch("apps.jobs.services.repurposer.time.sleep")
    @patch("apps.jobs.services.repurposer.requests.post")
    def test_does_not_retry_on_401(self, mock_post, mock_sleep):
        response = Mock()
        response.raise_for_status.side_effect = _http_error_with_status(401)
        mock_post.return_value = response

        with self.assertRaises(requests.exceptions.HTTPError):
            repurposer.call_openrouter("content", "openai/gpt-4o", "email")

        self.assertEqual(mock_post.call_count, 1)
        mock_sleep.assert_not_called()


class CallGeminiRetryTests(SimpleTestCase):
    @patch("apps.jobs.services.repurposer.types")
    @patch("apps.jobs.services.repurposer.time.sleep")
    @patch("apps.jobs.services.repurposer._get_gemini_client")
    def test_retries_transient_sdk_error_then_succeeds(
        self, mock_get_client, mock_sleep, mock_types
    ):
        mock_response = Mock()
        mock_response.candidates = [Mock()]
        mock_response.text = "generated tldr"
        mock_response.usage_metadata.candidates_token_count = 42

        mock_client = Mock()
        mock_client.models.generate_content.side_effect = [
            Exception("transient SDK error"),
            mock_response,
        ]
        mock_get_client.return_value = mock_client

        result = repurposer.call_gemini("content", "tldr")

        self.assertEqual(result["text"], "generated tldr")
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        mock_sleep.assert_called_once_with(repurposer.RETRY_BACKOFF_SECONDS[0])

    @patch("apps.jobs.services.repurposer.types")
    @patch("apps.jobs.services.repurposer.time.sleep")
    @patch("apps.jobs.services.repurposer._get_gemini_client")
    def test_raises_valueerror_after_exhausting_retries(
        self, mock_get_client, mock_sleep, mock_types
    ):
        mock_client = Mock()
        mock_client.models.generate_content.side_effect = Exception("still failing")
        mock_get_client.return_value = mock_client

        with self.assertRaises(ValueError):
            repurposer.call_gemini("content", "tldr")

        self.assertEqual(
            mock_client.models.generate_content.call_count, repurposer.RETRY_MAX_ATTEMPTS
        )


class RepurposeContinuesAfterFallbackExhaustionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="retry-test@example.com", password="pass123", full_name="Retry Tester"
        )
        self.job = Job.objects.create(
            user=self.user, content="blog content", model="openai/gpt-4o"
        )

    @patch("apps.jobs.services.repurposer.time.sleep")
    @patch("apps.jobs.services.repurposer.call_gemini")
    @patch("apps.jobs.services.repurposer.call_openrouter")
    def test_one_format_exhausting_both_providers_does_not_abort_job(
        self, mock_openrouter, mock_gemini, mock_sleep
    ):
        good_result = {
            "text": "generated",
            "latency_ms": 500,
            "tokens_generated": 100,
            "tokens_per_second": 200.0,
        }

        def openrouter_side_effect(original_content, model_used, format_used):
            if format_used == "email":
                raise requests.exceptions.Timeout("openrouter down")
            return good_result

        mock_openrouter.side_effect = openrouter_side_effect
        mock_gemini.side_effect = ValueError("Gemini SDK call failed: still down")

        results = repurposer.repurpose(self.job)

        formats = {r["format"] for r in results}
        self.assertNotIn("email", formats)
        self.assertEqual(len(results), 3)


class LoggingFieldsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="logfields@example.com", password="pass123", full_name="Log Fields"
        )
        self.job = Job.objects.create(
            user=self.user, content="blog content", model="openai/gpt-4o"
        )

    @patch("apps.jobs.services.repurposer.call_openrouter")
    def test_failure_log_includes_job_id_and_format(self, mock_call):
        mock_call.side_effect = Exception("boom")

        with self.assertLogs("apps.jobs.services.repurposer", level="ERROR") as caplog:
            repurposer.repurpose(self.job)

        record = caplog.records[0]
        self.assertEqual(record.job_id, str(self.job.id))
        self.assertIn(record.format, repurposer.SYSTEM_PROMPTS.keys())
