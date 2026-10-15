"""Regression tests for later execution; no cluster is required."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from devops_toolkit.cli import (Kube, QueryError, check_capacity, incident,
                               pod_requests, preflight, quantity, redact, write_private)


class FakeKube:
    def __init__(self, objects=None, keys=None):
        self.objects = objects or {}
        self.keys = keys or {}

    def get(self, kind, *args):
        value = self.objects.get(kind, {"items": []})
        if isinstance(value, Exception):
            raise value
        return value

    def reference_keys(self, kind, name):
        return self.keys.get((kind, name), [])


def deployment():
    return {"kind": "Deployment", "metadata": {"name": "platform"},
            "spec": {"template": {"spec": {"containers": [{
                "name": "api", "image": "ghcr.io/example/api@sha256:" + "a" * 64,
                "resources": {"requests": {"cpu": "100m", "memory": "32Mi"},
                              "limits": {"cpu": "500m", "memory": "128Mi"}},
                "readinessProbe": {"httpGet": {"path": "/health/ready", "port": 8080}},
                "livenessProbe": {"httpGet": {"path": "/health/live", "port": 8080}},
            }]}}}}


class ToolkitTests(unittest.TestCase):
    def test_quantity_units(self):
        self.assertEqual(quantity("500m"), quantity("0.5"))
        self.assertEqual(quantity("1Gi"), quantity("1024Mi"))
        for value in ("NaN", "-1", "Infinity", "not-a-quantity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                quantity(value)

    def test_init_and_overhead_accounting(self):
        spec = {"containers": [{"resources": {"requests": {"cpu": "100m"}}}],
                "initContainers": [{"resources": {"requests": {"cpu": "500m"}}}],
                "overhead": {"cpu": "50m"}}
        self.assertEqual(pod_requests(spec)["cpu"], quantity("550m"))

    def test_sidecar_resources_are_reported_as_unsupported(self):
        with self.assertRaises(ValueError):
            pod_requests({"initContainers": [{"restartPolicy": "Always"}]})

    def test_capacity_subtracts_existing_pod_requests(self):
        node = {"metadata": {"name": "n1"}, "spec": {},
                "status": {"conditions": [{"type": "Ready", "status": "True"}],
                           "allocatable": {"cpu": "1", "memory": "1Gi"}}}
        existing = {"spec": {"nodeName": "n1", "containers": [
            {"resources": {"requests": {"cpu": "900m"}}}]}, "status": {"phase": "Running"}}
        kube = FakeKube({"nodes": {"items": [node]}, "pods": {"items": [existing]}})
        wanted = {"containers": [{"resources": {"requests": {"cpu": "200m"}}}]}
        self.assertEqual(check_capacity(kube, wanted), [])

    def test_missing_secret_blocks_preflight(self):
        document = deployment()
        document["spec"]["template"]["spec"]["containers"][0]["env"] = [{
            "name": "TOKEN", "valueFrom": {"secretKeyRef": {"name": "app-token", "key": "token"}}}]
        args = argparse.Namespace(namespace="platform", deployment="platform",
                                  file=None, verify_images=False)
        result = preflight(FakeKube({"deployment": document}), args)
        self.assertTrue(any(c["status"] == "FAIL" and c["check"] == "reference:secret/app-token"
                            for c in result["checks"]))

    def test_optional_reference_does_not_block(self):
        document = deployment()
        document["spec"]["template"]["spec"]["containers"][0]["envFrom"] = [{
            "secretRef": {"name": "optional-token", "optional": True}}]
        args = argparse.Namespace(namespace="platform", deployment="platform",
                                  file=None, verify_images=False)
        result = preflight(FakeKube({"deployment": document}), args)
        self.assertFalse(any(c["check"].startswith("reference:") for c in result["checks"]))

    def test_binary_configmap_key_is_not_valid_for_env(self):
        document = deployment()
        document["spec"]["template"]["spec"]["containers"][0]["env"] = [{
            "name": "CONFIG", "valueFrom": {"configMapKeyRef": {"name": "cfg", "key": "file"}}}]
        args = argparse.Namespace(namespace="platform", deployment="platform",
                                  file=None, verify_images=False)
        result = preflight(FakeKube({"deployment": document},
                                   {("configmap", "cfg"): ["cfg", "binary:file"]}), args)
        self.assertTrue(any(c["status"] == "FAIL" and c["check"] == "reference:configmap/cfg"
                            for c in result["checks"]))

    def test_common_log_credentials_are_redacted(self):
        text = redact('password=abc token: xyz Authorization: Bearer abc.def '
                      'https://user:pass@example.com/path')
        for value in ("password=abc", "token: xyz", "abc.def", "user:pass"):
            self.assertNotIn(value, text)

    def test_private_report_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "report.json"
            write_private(path, "{}")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                write_private(path, "replacement")
            self.assertEqual(json.loads(path.read_text()), {})

    def test_snapshot_excludes_environment_annotations_and_event_messages(self):
        pod = {"metadata": {"name": "api-1", "annotations": {"private": "private-marker"}},
               "spec": {"containers": [{"name": "api", "image": "example/api",
                                        "env": [{"name": "TOKEN", "value": "private-marker"}]}]},
               "status": {"phase": "Running"}}
        event = {"reason": "BackOff", "message": "private-marker"}
        kube = FakeKube({"pods": {"items": [pod]}, "events": {"items": [event]}})
        with tempfile.TemporaryDirectory() as root:
            args = argparse.Namespace(output=str(Path(root) / "snapshot"),
                                      max_pods=10, include_logs=False)
            directory, report = incident(kube, args)
            self.assertNotIn("private-marker", json.dumps(report))
            self.assertEqual(report["logs"], [])
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)

    def test_kubectl_error_does_not_expose_stderr(self):
        result = argparse.Namespace(returncode=1, stdout=b"", stderr=b"private-marker")
        with patch("devops_toolkit.cli.subprocess.run", return_value=result):
            with self.assertRaises(QueryError) as caught:
                Kube("lab", "platform").run("get", "pods")
        self.assertNotIn("private-marker", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
