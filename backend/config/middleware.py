"""
Request correlation for ContentFlow AI.

Responsibility:
    Generate (or adopt) a per-request ID, expose it on the request object,
    echo it back as a response header, and make it available to every log
    line emitted during the request via a ContextVar + logging.Filter pair
    — without threading it through every function signature.
"""

import logging
import re
import uuid
import contextvars

# Shared across the process; each request gets its own value for the
# duration of that request via ContextVar's async/thread-safe scoping.
request_id_var: contextvars.ContextVar = contextvars.ContextVar(
    "request_id", default=None
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


class RequestIDMiddleware:
    """
    Assigns request.request_id, binds it into request_id_var for the
    duration of the request, and echoes it back as X-Request-Id.

    A client-supplied X-Request-Id header is only reused if it is a
    well-formed UUID — an arbitrary attacker-controlled string is never
    written into logs verbatim, since that would allow log injection.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        client_supplied = request.META.get("HTTP_X_REQUEST_ID", "")
        request_id = (
            client_supplied if _UUID_RE.match(client_supplied) else str(uuid.uuid4())
        )
        request.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-Id"] = request_id
        return response


class RequestIDLogFilter(logging.Filter):
    """Attaches the current request's ID (or "-" outside a request) to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True
