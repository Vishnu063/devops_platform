"""Release identity, health checks and bounded HTTP metrics."""
import json
import logging
import os
import time

from flask import Flask, Response, g, jsonify, request
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from werkzeug.exceptions import HTTPException

LOG = logging.getLogger("platform")


def create_app():
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16384, MAX_FORM_MEMORY_SIZE=16384)
    registry = CollectorRegistry()
    requests = Counter("platform_http_requests_total", "Completed HTTP requests",
                       ["method", "route", "status"], registry=registry)
    latency = Histogram("platform_http_request_duration_seconds", "HTTP request duration",
                        ["method", "route"], registry=registry,
                        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
    version = os.getenv("APP_VERSION", "local")

    @app.before_request
    def start_request():
        g.started = time.monotonic()

    @app.after_request
    def record_request(response):
        # Labels use the matched route, never arbitrary user paths or queries.
        route = request.url_rule.rule if request.url_rule else "unmatched"
        method = request.method if request.method in {"GET", "HEAD", "POST", "OPTIONS"} else "OTHER"
        elapsed = time.monotonic() - g.started
        if route not in {"/metrics", "/health/live", "/health/ready"}:
            requests.labels(method, route, str(response.status_code)).inc()
            latency.labels(method, route).observe(elapsed)
            LOG.info(json.dumps({"method": method, "route": route,
                                 "status": response.status_code,
                                 "duration_ms": round(elapsed * 1000, 2)}))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    @app.get("/")
    def release():
        return jsonify(service="devops-platform", version=version)

    @app.get("/api/integrations")
    def integrations():
        # No implicit kubectl context, credentials, remote fetch or mutation.
        return jsonify(kubernetes={"status": "disconnected", "reason": "Select an explicit context with the read-only toolkit"},
                       argocd={"status": "disconnected"}, helm={"status": "disconnected"},
                       ops_pilot={"status": "configured" if os.getenv("OPS_PILOT_EVENTS_URL") else "disabled",
                                  "scope": "Optional external event ingestion; connectivity not inferred"})

    @app.get("/ecosystem")
    def ecosystem():
        return Response("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>DevOps Platform connections</title>
<h1>DevOps Platform connections</h1><p>Kubernetes: disconnected. Argo CD: disconnected. Helm: disconnected.</p>
<p>This view opens without a cluster. No infrastructure is contacted or changed.</p>
<p>Use the existing toolkit with an explicit context for pod/deployment status, events, release checks and saved HTML reports.</p>
<p>CloudLaunch → Prometheus / Alertmanager → Ops Pilot → human approval → recovery verification.</p>
<p>Ops Pilot owns incident approvals. See /api/integrations for configured integration status.</p></html>""", content_type="text/html")

    @app.get("/health/live")
    def live():
        return jsonify(status="alive")

    @app.get("/health/ready")
    def ready():
        # This service has no downstream dependency.
        return jsonify(status="ready")

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(registry), content_type=CONTENT_TYPE_LATEST)

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = error.get_response()
        response.data = json.dumps({"error": error.name.lower()})
        response.content_type = "application/json"
        return response

    @app.errorhandler(Exception)
    def unexpected_error(error):
        LOG.exception("Unhandled request error")
        return jsonify(error="internal server error"), 500

    return app
