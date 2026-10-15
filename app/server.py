"""Stateless release-status service for deployment and incident exercises."""
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = logging.getLogger("platform")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health/live":
            self.respond(200, {"status": "alive"})
        elif path == "/health/ready":
            self.respond(200, {"status": "ready"})
        elif path == "/":
            self.respond(200, {"service": "devops-platform",
                               "version": os.getenv("APP_VERSION", "local")})
        elif path == "/metrics":
            body = b'# HELP platform_up Service availability\n# TYPE platform_up gauge\nplatform_up 1\n'
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.respond(404, {"error": "not found"})

    def respond(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        LOG.info(json.dumps({"client": self.client_address[0], "request": fmt % args}))


def main():
    logging.basicConfig(level=logging.INFO)
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
