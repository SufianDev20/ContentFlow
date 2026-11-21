"""
LLM providers: OpenRouter (primary) and Gemini.

`generate()` is the only entry point for producing text. A Gemini model id is
sent to Gemini; anything else goes to OpenRouter, falling back to Gemini's
default model if OpenRouter fails.
"""

import functools
import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/free"
FREE_MODEL_FALLBACK = "meta-llama/llama-3.1-8b-instruct:free"
GEMINI_FREE_MODELS = [
    "gemini-3.1-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it",
]

# (connect, read) seconds. Long posts can take 20-40 s to generate.
REQUEST_TIMEOUT = (10, 60)
TEMPERATURE = 0.7
MAX_OUTPUT_TOKENS = 1024

RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (0.5, 1.5)


class ProviderError(Exception):
    """The provider answered, but not with usable generated text."""


@dataclass(frozen=True)
class Generation:
    text: str
    provider: str
    latency_ms: int
    tokens_generated: int
    tokens_per_second: float


def _is_transient_http_error(exc: Exception) -> bool:
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code >= 500
    return False


def _call_with_retry(fn, is_retryable, log_label):
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_retryable(exc) or attempt == RETRY_MAX_ATTEMPTS:
                raise
            delay = RETRY_BACKOFF_SECONDS[attempt - 1]
            logger.warning(
                "%s attempt %d failed (%s); retrying in %ss", log_label, attempt, exc, delay
            )
            time.sleep(delay)


def _timed_generation(provider: str, call) -> Generation:
    """Run call() -> (text, tokens_generated) and attach latency metrics."""
    start = time.monotonic()
    text, tokens = call()
    elapsed_ms = int((time.monotonic() - start) * 1000)
    seconds = elapsed_ms / 1000
    return Generation(
        text=text,
        provider=provider,
        latency_ms=elapsed_ms,
        tokens_generated=tokens,
        tokens_per_second=round(tokens / seconds, 2) if seconds > 0 else 0.0,
    )


def _openrouter_call(model: str, system_prompt: str, content: str):
    def request():
        resp = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "127.0.0.1:9000",
                "X-Title": "ContentFlow AI",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                "temperature": TEMPERATURE,
                "max_completion_tokens": MAX_OUTPUT_TOKENS,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    data = _call_with_retry(request, _is_transient_http_error, "OpenRouter")
    if "error" in data:
        raise ProviderError(f"OpenRouter error: {data['error'].get('message', data['error'])}")
    if not data.get("choices"):
        raise ProviderError(f"Unexpected OpenRouter response: {data}")
    tokens = data.get("usage", {}).get("completion_tokens", 0)
    return data["choices"][0]["message"]["content"], tokens


@functools.cache
def _gemini_client():
    from google import genai  # imported here so Gemini is only needed when used

    if not settings.GEMINI_API_KEY:
        raise ProviderError("GEMINI_API_KEY not configured")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _gemini_call(model: str, system_prompt: str, content: str):
    from google.genai import types

    client = _gemini_client()

    def request():
        return client.models.generate_content(
            model=model,
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=TEMPERATURE,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            ),
        )

    # The SDK has no stable exception type separating transient from permanent
    # failures, so every error is retried.
    response = _call_with_retry(request, lambda exc: True, "Gemini")
    if not response.candidates:
        raise ProviderError(f"Unexpected Gemini response: {response}")
    return response.text, getattr(response.usage_metadata, "candidates_token_count", 0) or 0


def generate(model: str, system_prompt: str, content: str) -> Generation:
    if model in GEMINI_FREE_MODELS or model.startswith("gemini"):
        return _timed_generation("gemini", lambda: _gemini_call(model, system_prompt, content))
    try:
        return _timed_generation("openrouter", lambda: _openrouter_call(model, system_prompt, content))
    except (requests.exceptions.RequestException, ProviderError) as exc:
        logger.warning("OpenRouter failed (%s); falling back to Gemini", exc)
        return _timed_generation(
            "gemini",
            lambda: _gemini_call(settings.GEMINI_FALLBACK_MODEL, system_prompt, content),
        )


def available_models() -> dict[str, list[str]]:
    """Free-tier model ids per provider. OpenRouter is queried live."""
    try:
        response = requests.get(
            f"{OPENROUTER_BASE_URL}/models",
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
            timeout=(5, 15),
        )
        response.raise_for_status()
        openrouter = [m["id"] for m in response.json().get("data", []) if m["id"].endswith(":free")]
    except Exception:
        logger.exception("Failed to fetch free model list from OpenRouter")
        openrouter = []

    return {
        "openrouter": openrouter or [FREE_MODEL_FALLBACK],
        "gemini": GEMINI_FREE_MODELS if settings.GEMINI_API_KEY else [],
    }


def all_model_ids() -> list[str]:
    return [model for ids in available_models().values() for model in ids]
