from unittest.mock import patch
from django.test import TestCase


class HealthCheckTests(TestCase):
    def test_returns_200_and_ok_status_when_db_is_healthy(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["db"], "ok")

    @patch("config.views.connection")
    def test_returns_503_when_db_query_fails(self, mock_connection):
        mock_connection.cursor.side_effect = Exception("connection refused")

        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["db"], "error")

    def test_does_not_require_authentication(self):
        # No credentials/JWT provided; must still succeed (or 503 on DB
        # trouble), never 401/403.
        response = self.client.get("/health/")
        self.assertIn(response.status_code, (200, 503))
