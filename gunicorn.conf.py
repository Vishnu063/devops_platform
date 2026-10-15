"""One process per pod keeps Prometheus metrics local and consistent."""
import logging

bind = "0.0.0.0:8080"
workers = 1
worker_class = "gthread"
threads = 4
timeout = 30
graceful_timeout = 20
keepalive = 2
max_requests = 10000
max_requests_jitter = 1000
worker_tmp_dir = "/tmp"
limit_request_line = 2048
limit_request_fields = 50
limit_request_field_size = 4096
# Do not trust forwarded headers from arbitrary clients.
forwarded_allow_ips = ""
accesslog = None
errorlog = "-"
capture_output = True
logging.basicConfig(level=logging.INFO, format="%(message)s")
control_socket_disable = True
