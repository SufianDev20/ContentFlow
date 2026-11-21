import json
import logging

from config.logging_utils import JsonFormatter


def render(message, exc_info=None, **extra):
    record = logging.LogRecord("test.logger", logging.WARNING, __file__, 1, message, None, exc_info)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_message_with_quotes_and_newlines_stays_valid_json():
    message = 'Provider returned: {"error": "bad \\"nested\\" quote"}\nline two'

    assert render(message)["message"] == message


def test_core_and_structured_fields_are_included_when_present():
    entry = render("hi", request_id="req-1", job_id="abc", format="tldr")

    assert entry["level"] == "WARNING"
    assert entry["logger"] == "test.logger"
    assert (entry["request_id"], entry["job_id"], entry["format"]) == ("req-1", "abc", "tldr")


def test_structured_fields_are_omitted_when_absent():
    entry = render("hi")

    assert not {"request_id", "job_id", "format"} & entry.keys()


def test_exception_traceback_is_included():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        entry = render("failed", exc_info=sys.exc_info())

    assert "ValueError: boom" in entry["exc_info"]
