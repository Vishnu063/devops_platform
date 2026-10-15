import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

from app.server import Handler


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self, path):
        return urlopen(self.url + path, timeout=3)

    def test_health(self):
        for route, status in [("/health/live", "alive"), ("/health/ready", "ready")]:
            with self.subTest(route=route), self.get(route) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response)["status"], status)

    def test_release_identity_and_headers(self):
        with patch.dict(os.environ, {"APP_VERSION": "abc123"}):
            with self.get("/?check=true") as response:
                self.assertEqual(json.load(response)["version"], "abc123")
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_metrics(self):
        with self.get("/metrics") as response:
            self.assertIn("text/plain", response.headers["Content-Type"])
            self.assertIn(b"platform_up 1", response.read())

    def test_unknown_route(self):
        with self.assertRaises(HTTPError) as context:
            self.get("/unknown")
        self.assertEqual(context.exception.code, 404)
        self.assertEqual(json.load(context.exception), {"error": "not found"})


if __name__ == "__main__":
    unittest.main()
