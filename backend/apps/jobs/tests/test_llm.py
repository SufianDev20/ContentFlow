from unittest.mock import Mock, patch

import pytest
import requests

from apps.jobs.services import llm


def http_error(status_code):
    response = requests.models.Response()
    response.status_code = status_code
    return requests.exceptions.HTTPError(f"{status_code}", response=response)


def openrouter_reply(text="generated", tokens=10):
    reply = Mock()
    reply.json.return_value = {
        "choices": [{"message": {"content": text}}],
        "usage": {"completion_tokens": tokens},
    }
    return reply


def failing_reply(status_code):
    reply = Mock()
    reply.raise_for_status.side_effect = http_error(status_code)
    return reply


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("apps.jobs.services.llm.time.sleep") as sleep:
        yield sleep


@pytest.fixture
def post():
    with patch("apps.jobs.services.llm.requests.post") as post:
        yield post


@pytest.fixture
def gemini(settings):
    settings.GEMINI_API_KEY = "key"
    settings.GEMINI_FALLBACK_MODEL = "gemini-fallback"
    response = Mock(candidates=[Mock()], text="from gemini")
    response.usage_metadata.candidates_token_count = 42
    client = Mock()
    client.models.generate_content.return_value = response
    with patch("apps.jobs.services.llm._gemini_client", return_value=client), patch.dict(
        "sys.modules", {"google": Mock(), "google.genai": Mock(), "google.genai.types": Mock()}
    ):
        yield client


class TestOpenRouter:
    def test_returns_text_with_metrics(self, post):
        post.return_value = openrouter_reply("hello", tokens=200)
        with patch("apps.jobs.services.llm.time.monotonic", side_effect=[0.0, 2.0]):
            result = llm.generate("openai/gpt-4o", "system", "content")

        assert result == llm.Generation(
            text="hello",
            provider="openrouter",
            latency_ms=2000,
            tokens_generated=200,
            tokens_per_second=100.0,
        )

    def test_sends_model_and_both_messages(self, post):
        post.return_value = openrouter_reply()

        llm.generate("openai/gpt-4o", "the system prompt", "the blog post")

        body = post.call_args.kwargs["json"]
        assert body["model"] == "openai/gpt-4o"
        assert body["messages"] == [
            {"role": "system", "content": "the system prompt"},
            {"role": "user", "content": "the blog post"},
        ]

    def test_transient_server_error_is_retried(self, post, no_sleep):
        post.side_effect = [failing_reply(502), openrouter_reply("ok")]

        assert llm.generate("m", "s", "c").text == "ok"
        assert post.call_count == 2
        no_sleep.assert_called_once_with(llm.RETRY_BACKOFF_SECONDS[0])

    def test_retries_stop_after_the_attempt_budget(self, post, gemini):
        post.return_value = failing_reply(503)

        llm.generate("m", "s", "c")

        assert post.call_count == llm.RETRY_MAX_ATTEMPTS


class TestFallbackToGemini:
    def test_client_error_falls_back_without_retrying(self, post, gemini):
        post.return_value = failing_reply(401)

        result = llm.generate("m", "s", "c")

        assert post.call_count == 1
        assert (result.provider, result.text, result.tokens_generated) == ("gemini", "from gemini", 42)
        assert gemini.models.generate_content.call_args.kwargs["model"] == "gemini-fallback"

    @pytest.mark.parametrize(
        "body", [{"error": {"message": "no credits"}}, {"choices": []}, {}]
    )
    def test_unusable_openrouter_answer_falls_back(self, post, gemini, body):
        post.return_value = Mock(json=Mock(return_value=body))

        assert llm.generate("m", "s", "c").provider == "gemini"

    def test_gemini_failure_after_fallback_propagates(self, post, gemini):
        post.return_value = failing_reply(401)
        gemini.models.generate_content.side_effect = RuntimeError("down")

        with pytest.raises(RuntimeError):
            llm.generate("m", "s", "c")
        assert gemini.models.generate_content.call_count == llm.RETRY_MAX_ATTEMPTS


class TestGeminiModelRouting:
    def test_gemini_model_goes_straight_to_gemini_with_that_model(self, post, gemini):
        result = llm.generate("gemini-2.5-flash", "s", "c")

        post.assert_not_called()
        assert result.provider == "gemini"
        assert gemini.models.generate_content.call_args.kwargs["model"] == "gemini-2.5-flash"

    def test_gemma_models_are_routed_to_gemini_too(self, post, gemini):
        llm.generate("gemma-4-31b-it", "s", "c")

        post.assert_not_called()


class TestAvailableModels:
    @pytest.fixture
    def listing(self):
        with patch("apps.jobs.services.llm.requests.get") as get:
            yield get

    def test_keeps_only_free_openrouter_models(self, listing, settings):
        settings.GEMINI_API_KEY = ""
        listing.return_value.json.return_value = {
            "data": [{"id": "a/free-one:free"}, {"id": "b/paid"}]
        }

        assert llm.available_models() == {"openrouter": ["a/free-one:free"], "gemini": []}

    def test_gemini_models_need_an_api_key(self, listing, settings):
        settings.GEMINI_API_KEY = "key"
        listing.return_value.json.return_value = {"data": []}

        result = llm.available_models()

        assert result["gemini"] == llm.GEMINI_FREE_MODELS
        assert result["openrouter"] == [llm.FREE_MODEL_FALLBACK]

    def test_openrouter_outage_falls_back_to_default_model(self, listing, settings):
        settings.GEMINI_API_KEY = ""
        listing.side_effect = requests.exceptions.ConnectionError()

        assert llm.available_models()["openrouter"] == [llm.FREE_MODEL_FALLBACK]
