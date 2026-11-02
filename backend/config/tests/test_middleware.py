import re
import uuid
import logging
from django.test import SimpleTestCase, RequestFactory
from config.middleware import RequestIDMiddleware, RequestIDLogFilter, request_id_var

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


class _FakeResponse(dict):
    """Minimal stand-in for an HttpResponse exposing a mutable .headers dict."""

    def __init__(self):
        super().__init__()
        self.headers = {}


class RequestIDMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_generates_uuid_when_no_header_present(self):
        seen = {}

        def get_response(request):
            seen["request_id"] = request.request_id
            seen["contextvar_value"] = request_id_var.get()
            return _FakeResponse()

        middleware = RequestIDMiddleware(get_response)
        request = self.factory.get("/")
        response = middleware(request)

        self.assertTrue(UUID_RE.match(seen["request_id"]))
        self.assertEqual(seen["contextvar_value"], seen["request_id"])
        self.assertEqual(response.headers["X-Request-Id"], seen["request_id"])

    def test_reuses_well_formed_uuid_from_client_header(self):
        client_id = str(uuid.uuid4())

        def get_response(request):
            return _FakeResponse()

        middleware = RequestIDMiddleware(get_response)
        request = self.factory.get("/", HTTP_X_REQUEST_ID=client_id)
        response = middleware(request)

        self.assertEqual(response.headers["X-Request-Id"], client_id)

    def test_ignores_malformed_client_header_and_generates_new_id(self):
        def get_response(request):
            return _FakeResponse()

        middleware = RequestIDMiddleware(get_response)
        request = self.factory.get("/", HTTP_X_REQUEST_ID="'; DROP TABLE jobs; --")
        response = middleware(request)

        self.assertTrue(UUID_RE.match(response.headers["X-Request-Id"]))

    def test_contextvar_is_reset_after_request(self):
        def get_response(request):
            return _FakeResponse()

        middleware = RequestIDMiddleware(get_response)
        request = self.factory.get("/")
        middleware(request)

        self.assertIsNone(request_id_var.get())


class RequestIDLogFilterTests(SimpleTestCase):
    def test_attaches_contextvar_value_to_record(self):
        token = request_id_var.set("abc-123")
        try:
            record = logging.LogRecord(
                "test", logging.INFO, __file__, 1, "message", None, None
            )
            RequestIDLogFilter().filter(record)
            self.assertEqual(record.request_id, "abc-123")
        finally:
            request_id_var.reset(token)

    def test_defaults_to_dash_when_no_request_in_progress(self):
        record = logging.LogRecord(
            "test", logging.INFO, __file__, 1, "message", None, None
        )
        RequestIDLogFilter().filter(record)
        self.assertEqual(record.request_id, "-")
