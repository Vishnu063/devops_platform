import os
import unittest
from unittest.mock import patch

from app.server import create_app


class ServiceTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"APP_VERSION": "abc123"}):
            self.app = create_app()
        self.client = self.app.test_client()

    def test_health(self):
        for route, status in [("/health/live", "alive"), ("/health/ready", "ready")]:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, {"status": status})

    def test_identity_and_headers(self):
        response = self.client.get("/?token=must-not-be-logged")
        self.assertEqual(response.json["version"], "abc123")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_metrics_and_bounded_labels(self):
        self.client.get("/")
        self.client.get("/unknown-one")
        self.client.get("/unknown-two")
        response = self.client.get("/metrics")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("platform_http_requests_total", body)
        self.assertIn('route="unmatched"', body)
        self.assertNotIn("unknown-one", body)
        self.assertNotIn("unknown-two", body)

    def test_missing_and_disallowed_method(self):
        self.assertEqual(self.client.get("/missing").status_code, 404)
        response = self.client.post("/")
        self.assertEqual(response.status_code, 405)
        self.assertIn("GET", response.headers["Allow"])

    def test_head(self):
        response = self.client.head("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"")

    def test_internal_errors_do_not_expose_details(self):
        @self.app.get("/failure")
        def fail():
            raise RuntimeError("private-detail")
        with self.assertLogs("platform", level="ERROR"):
            response = self.client.get("/failure")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json, {"error": "internal server error"})
        self.assertNotIn("private-detail", response.get_data(as_text=True))

    def test_query_values_not_logged(self):
        with self.assertLogs("platform", level="INFO") as captured:
            self.client.get("/?token=private-value")
        self.assertNotIn("private-value", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
