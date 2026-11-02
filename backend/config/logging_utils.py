"""JSON log formatter for production logging."""

import json
import logging

# Structured fields copied onto the JSON payload when present on the
# LogRecord (attached via logging's extra= kwarg at the call site, or by
# RequestIDLogFilter for request_id).
_STRUCTURED_FIELDS = ("request_id", "job_id", "format")


class JsonFormatter(logging.Formatter):
    """Formats each log record as a single line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)
