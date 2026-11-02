"""
OpenRouter LLM Integration service for ContentFlow AI.

Responsibility:
   Transform blog post text into one or more platform-ready content formats by calling OpenRouter chat completions API. Returns structured data ready to be saved as Output model instances.
OpenRouter API References:
   POST:https://openrouter.ai/api/v1/chat/completions Main URL endpoint for AI models to be called and used.
   Auth: Bearer Token via Authorization Header.
    Schema: OpenAI-compatible — choices[0].message.content holds the text, usage.completion_tokens and usage.prompt_tokens hold token counts.
    Docs:  https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request

Usage:
    from apps.jobs.services.repurposer import repurpose
    outputs = repurpose(job)   # returns list[dict], one per format
"""

import logging, time, requests, typing, re
from django.conf import settings
from apps.stats.models import Output
from apps.jobs.services.quality_score import score

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - dependency may be absent in local dev env
    genai = None
    types = None

logger = logging.getLogger(__name__)

# Global Gemini client (initialized lazily)
_gemini_client = None

# OpenRouter endpoint — stable as of June 2025.
# Source: https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
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
GEMINI_MODEL_PREFIX = "gemini"
# HTTP timeout: 10 s to connect, 60 s to read.
# LLM responses for long blog posts can take 20–40 s depending on model.
REQUEST_TIMEOUT = (10, 60)

# Retry budget for transient provider failures: 1 initial attempt + 2
# retries, with exponential backoff between attempts.
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (0.5, 1.5)


def _is_retryable_http_error(exc: Exception) -> bool:
    """
    True if exc represents a transient failure worth retrying.

    Retries network-level failures (timeout, connection refused/reset) and
    HTTP 5xx responses. Does not retry HTTP 4xx (bad request/auth — retrying
    won't help) or response-shape errors (ValueError, KeyError — also not
    transient).
    """
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        return status is not None and status >= 500
    return False


def _call_with_retry(fn, is_retryable, log_label, extra=None):
    """
    Call fn() with exponential backoff retry on transient failures.

    Args:
        fn: Zero-arg callable performing the actual provider request.
        is_retryable: Predicate(exception) -> bool deciding whether a given
            failure is worth retrying.
        log_label: Short string identifying the provider in log messages,
            e.g. "OpenRouter" or "Gemini".
        extra: Optional dict of structured logging fields (e.g. job_id,
            format) attached to the retry warning log line.

    Returns:
        Whatever fn() returns on success.

    Raises:
        The triggering exception, either immediately (not retryable) or
        after RETRY_MAX_ATTEMPTS attempts are exhausted.
    """
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_retryable(exc) or attempt == RETRY_MAX_ATTEMPTS:
                raise
            delay = RETRY_BACKOFF_SECONDS[attempt - 1]
            logger.warning(
                f"{log_label} attempt {attempt} failed ({exc}); retrying in {delay}s",
                extra=extra or {},
            )
            time.sleep(delay)


# Per-format system prompts. Each instructs the model precisely so output
# needs no post-processing before display.
SYSTEM_PROMPTS: dict[str, str] = {
    "tweet_thread": (
        "You are a social media expert. Convert the blog post into a Twitter/X thread."
        "Number each tweet (1/, 2/, …). Keep every individual tweet under 280 characters. "
        "Aim for 5 - 10 tweets. Use plain text only, no markdown."
    ),
    "linkedin": (
        "You are a LinkedIn content strategist. Rewrite the blog post as a LinkedIn article."
        "Use a compelling opening hook, short paragraphs, and a clear call to action at the end. "
        "Target 150-300 words. Plain Text only.No markdown."
    ),
    "email": (
        "You are an email newsletter writer. Convert the blog post into a newsletter email. "
        "Include a subject line on the first line prefixed with 'Subject:', followed by the body. "
        "Keep it scannable with short paragraphs. Target 200-400 words. Plain text only."
    ),
    "tldr": (
        "You are a summarisation assistant. Read the blog post and extract its "
        "3 to 5 most important points. Write exactly one bullet per point, each "
        "starting with '•'. Each bullet must be a single sentence under 20 words. "
        "Do not repeat the same point across multiple bullets. Do not include an "
        "introduction, conclusion, or any text outside the bullets. Plain text only, "
        "no markdown, no numbering."
    ),
}


def is_gemini_model(model_id: str) -> bool:
    """True if model_id refers to a Gemini model, not an OpenRouter slug."""
    return model_id.startswith(GEMINI_MODEL_PREFIX)


def repurpose(job) -> list[dict]:
    """
    Generate platform-ready content for every format requested by a Job.

    This is the main entry point called by the job view or a background task.
    It iterates over the Output.FORMAT_CHOICES associated with the job and calls the OpenRouter API once per format.

    Args:
        job: A Job model instance. Must have:
            - job.content (str): blog post text to repurpose.
            - job.model (str): OpenRouter model slug, e.g. "openai gpt-4o".
            - job.outputs_requested (list[str]): list of format keys, eg.
              ["tweet_thread", "linkedin"]. If this attribute does not exist, all four formats are generated.

    Returns:
        list[dict]: List of dicts, one per format, each containing:
            {
                "format": str,           # e.g. "tweet_thread"
                "text": str,             # generated content
                "latency_ms": int,       # wall-clock ms for the API call
                "tokens_generated": int, # completion_tokens from API response
                "tokens_per_second": float,
            }
        Formats that fail are excluded from the list; errors are logged.
    Raises:
        Does not raise. Individual format failures are caught, logged, and skipped so one bad format does not abort the entire job.
    """
    formats = getattr(job, "formats", None)
    if not formats:
        formats = getattr(job, "outputs_requested", None)
    if not formats:
        formats = list(SYSTEM_PROMPTS.keys())
    if isinstance(formats, str):
        formats = [formats]
    results = []

    # Ensure model string is passed cleanly
    model_to_use = job.model if job.model else FREE_MODEL_FALLBACK

    for fmt in formats:
        if fmt not in SYSTEM_PROMPTS:
            logger.warning(f"Unknown format {fmt} requested for job {job.id}")
            continue
        try:
            result, provider = call_with_fallback(
                original_content=job.content,
                model_used=model_to_use,
                format_used=fmt,
            )
            result["format"] = fmt
            result["text"] = re.sub(r"\*\*(.*?)\*\*", r"\1", result["text"])
            Output.objects.create(
                job=job,
                format=fmt,
                text=result["text"],
                tokens_generated=result["tokens_generated"],
                latency_ms=result["latency_ms"],
                tokens_per_second=result["tokens_per_second"],
                character_count=len(result["text"]),
                provider=provider,
                quality_score=score(job.content, result["text"], fmt),
            )

            results.append(result)
        except Exception:
            logger.exception(
                f"OpenRouter call failed for job {job.id} format {fmt}",
                extra={"job_id": str(job.id), "format": fmt},
            )

    return results


def build_prompt(content: str, format_used: str) -> list[dict]:
    """
    Construct the messages array for the OpenRouter chat completion request.
    Uses a two-message structure:
       - system: format-specific instructions from SYSTEM_PROMPTS
       - user: the raw blog post text.
    Keeping instructions in the system role and content in the user role gives better results than combining both into one user message because the model treats system-role text as persistent context rather than a conversational turn.

    Args:
        content (str): Plain-text blog post content (from scraper or user input).
        format_used (str): One of the keys in _SYSTEM_PROMPTS:
                 "tweet_thread", "linkedin", "email", "tldr".

    Returns:
        list[dict]: Messages array ready to be passed as the "messages" key in the OpenRouter request body.
    Raises:
        KeyError: If fmt is not recognised format key.
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPTS[format_used]},
        {"role": "user", "content": content},
    ]


def call_openrouter(original_content: str, model_used: str, format_used: str) -> dict:
    """
    Send one chat completion request to OpenRouter and return parsed metrics.

    Request structure per OpenRouter docs:
        POST https://openrouter.ai/api/v1/chat/completions
        Authorization: Bearer <OPENROUTER_API_KEY>
        Content-Type: application/json
        Body: {
            "model": "<model-slug>",
            "messages": [...],
            "temperature": 0.7,
            "max_completion_tokens": 1024
        }

    Response structure (OpenAI-compatible schema):
        {
            "choices": [{"message": {"content": "<text>"}}],
            "usage": {
                "completion_tokens": <int>,
                "prompt_tokens": <int>,
                "total_tokens": <int>
            }
        }

    Args:
        original_content (str): Blog post plain text.
        model_used (str): OpenRouter model slug, e.g. "openai/gpt-4o", "anthropic/claude-3-haiku".
        format_used (str): Output format key used to select the system prompt.

    Returns:
        dict: Dict with keys: text, latency_ms, tokens_generated, tokens_per_second.
    Raises:
        requests.exceptions.Timeout:  API did not respond within _REQUEST_TIMEOUT.
        requests.exceptions.HTTPError: Non-2xx HTTP response from OpenRouter.
        KeyError: Unexpected response shape from OpenRouter.
    """
    OPENROUTER_API_KEY = settings.OPENROUTER_API_KEY
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referrer": "127.0.0.1:9000",
        "X-Title": "ContentFlow AI",
    }
    payload = {
        "model": model_used,
        "messages": build_prompt(original_content, format_used),
        # temperature=0.7 balances creativity with consistency.
        # 0.0 = deterministic, 1.0+ = more random. 0.7 is OpenRouter's
        # effective default for content generation tasks.
        "temperature": 0.7,
        # max_completion_tokens caps spend per call. 1024 tokens covers
        # a full tweet thread or LinkedIn post. tldr and email fit easily.
        "max_completion_tokens": 1024,
    }
    def _do_request():
        resp = requests.post(
            OPENROUTER_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
        )
        # Raises requests.exceptions.HTTPError for 4xx,5xx status code
        resp.raise_for_status()
        return resp

    start = time.monotonic()
    response = _call_with_retry(
        _do_request,
        is_retryable=_is_retryable_http_error,
        log_label="OpenRouter",
        extra={"format": format_used},
    )

    # how many milliseconds API call took before the response and till here after response.
    elapsed_ms = int((time.monotonic() - start) * 1000)

    data = response.json()

    if "error" in data:
        raise ValueError(
            f"OpenRouter Error: {data['error'].get('message', data['error'])}"
        )

    if "choices" not in data or not data["choices"]:
        raise KeyError(f"Unexpected response structure from OpenRouter: {data}")

    generated_text = data["choices"][0]["message"]["content"]
    # Safely extract usage tokens with defaults if usage block is missing
    usage = data.get("usage", {})
    tokens_generated = usage.get("completion_tokens", 0)

    # tokens-per-second: divided by elapsed seconds; guard against zero
    elapsed_seconds = elapsed_ms / 1000
    tokens_per_second = (
        round(tokens_generated / elapsed_seconds, 2) if elapsed_seconds > 0 else 0.0
    )
    logger.info(
        f"OpenRouter: model:{model_used} format:{format_used} tokens:{tokens_generated} latency:{elapsed_ms}"
    )
    return {
        "text": generated_text,
        "latency_ms": elapsed_ms,
        "tokens_generated": tokens_generated,
        "tokens_per_second": tokens_per_second,
    }


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not configured")
        _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _gemini_client


def call_gemini(
    original_content: str, format_used: str, model_used: str = None
) -> dict:
    """
    Calls Gemini via the google-genai SDK.

    Response object shape:
        response.text                                  -> generated string
        response.usage_metadata.candidates_token_count  -> completion tokens
    """
    client = _get_gemini_client()
    model_used = model_used or settings.GEMINI_FALLBACK_MODEL

    messages = build_prompt(original_content, format_used)
    system_text = messages[0]["content"]
    user_text = messages[1]["content"]

    def _do_generate():
        return client.models.generate_content(
            model=model_used,
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=system_text,
                temperature=0.7,
                max_output_tokens=1024,
            ),
        )

    start = time.monotonic()
    try:
        # The google-genai SDK doesn't expose a stable, version-independent
        # exception type distinguishing transient vs permanent failures, so
        # any exception raised here is treated as retryable.
        response = _call_with_retry(
            _do_generate,
            is_retryable=lambda exc: True,
            log_label="Gemini",
            extra={"format": format_used},
        )
    except Exception as e:
        raise ValueError(f"Gemini SDK call failed: {e}")
    elapsed_ms = int((time.monotonic() - start) * 1000)

    if not response.candidates:
        raise KeyError(f"Unexpected response structure from Gemini: {response}")

    generated_text = response.text
    tokens_generated = (
        getattr(response.usage_metadata, "candidates_token_count", 0) or 0
    )

    elapsed_seconds = elapsed_ms / 1000
    tokens_per_second = (
        round(tokens_generated / elapsed_seconds, 2) if elapsed_seconds > 0 else 0.0
    )

    logger.info(
        f"Gemini: model:{model_used} format:{format_used} tokens:{tokens_generated} latency:{elapsed_ms}"
    )
    return {
        "text": generated_text,
        "latency_ms": elapsed_ms,
        "tokens_generated": tokens_generated,
        "tokens_per_second": tokens_per_second,
    }


def call_with_fallback(
    original_content: str, model_used: str, format_used: str
) -> tuple[dict, str]:
    """
    Try OpenRouter first. On any failure, fall back to Gemini.
    Returns (result_dict, provider_name) so the caller can record which
    provider actually produced the output.
    """
    try:
        result = call_openrouter(original_content, model_used, format_used)
        return result, "openrouter"
    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        logger.warning(
            f"OpenRouter failed for job format {format_used} ({e}), falling back to Gemini"
        )
        result = call_gemini(original_content, format_used)
        return result, "gemini"


def get_available_free_model() -> list[str]:
    """
    Returns combined list of free-tier model IDs from OpenRouter and Gemini.
    OpenRouter models keep their existing slug format, e.g. "meta-llama/llama-3.1-8b-instruct:free".
    Gemini models are prefixed with "gemini-" already, so they are distinguishable
    in the dropdown without an extra namespace.
    """
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
            timeout=(5, 15),
        )
        response.raise_for_status()
        models = response.json().get("data", [])
        openrouter_free = [m["id"] for m in models if m["id"].endswith(":free")]
        if not openrouter_free:
            openrouter_free = [FREE_MODEL_FALLBACK]
    except Exception:
        logger.exception("Failed to fetch free model list from OpenRouter")
        openrouter_free = [FREE_MODEL_FALLBACK]

    gemini_free = GEMINI_FREE_MODELS if settings.GEMINI_API_KEY else []

    return openrouter_free + gemini_free
