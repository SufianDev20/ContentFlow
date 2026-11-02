import json
import logging
from django.test import SimpleTestCase
from config.logging_utils import JsonFormatter


class JsonFormatterTests(SimpleTestCase):
    def _make_record(self, message, **extra):
        record = logging.LogRecord(
            "test.logger", logging.INFO, __file__, 1, message, None, None
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return record

    def test_output_is_valid_json(self):
        record = self._make_record("plain message", request_id="req-1")
        output = JsonFormatter().format(record)
        parsed = json.loads(output)
        self.assertEqual(parsed["message"], "plain message")
        self.assertEqual(parsed["request_id"], "req-1")
        self.assertEqual(parsed["level"], "INFO")

    def test_valid_json_with_quotes_and_newlines_in_message(self):
        message = 'Provider returned: {"error": "bad \\"nested\\" quote"}\nline two'
        record = self._make_record(message)
        output = JsonFormatter().format(record)
        parsed = json.loads(output)  # raises if not valid JSON
        self.assertEqual(parsed["message"], message)

    def test_omits_optional_fields_when_absent(self):
        record = self._make_record("no extras here")
        output = JsonFormatter().format(record)
        parsed = json.loads(output)
        self.assertNotIn("job_id", parsed)
        self.assertNotIn("format", parsed)

    def test_includes_job_id_and_format_when_present(self):
        record = self._make_record("with extras", job_id="abc", format="tldr")
        output = JsonFormatter().format(record)
        parsed = json.loads(output)
        self.assertEqual(parsed["job_id"], "abc")
        self.assertEqual(parsed["format"], "tldr")
