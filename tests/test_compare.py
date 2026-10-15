"""Offline comparison regressions, supplied for later execution."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from devops_toolkit.cli import main
from devops_toolkit.compare import compare_files


def snapshot():
    return {"schema_version": 1, "context": "example", "namespace": "platform",
            "created_at": "2026-10-15T12:00:00+00:00",
            "pods": [{"name": "api-1", "uid": "uid-one", "phase": "Running",
                      "images": ["example/api@sha256:" + "a" * 64],
                      "containers": [{"name": "api", "ready": True, "restarts": 0}]}],
            "deployments": [{"name": "platform", "ready": 3, "desired": 3, "updated": 3,
                             "images": ["example/api@sha256:" + "a" * 64]}],
            "events": [], "unavailable": [], "pods_truncated": False}


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.before_path = Path(self.temp.name) / "before.json"
        self.after_path = Path(self.temp.name) / "after.json"
        self.before = snapshot()
        self.after = deepcopy(self.before)
        self.after["created_at"] = "2026-10-15T12:10:00+00:00"

    def save(self):
        self.before_path.write_text(json.dumps(self.before))
        self.after_path.write_text(json.dumps(self.after))

    def compare(self):
        self.save()
        return compare_files(self.before_path, self.after_path)

    def test_unchanged_snapshot(self):
        self.assertFalse(self.compare()["has_changes"])

    def test_image_replicas_and_restarts(self):
        self.after["deployments"][0]["images"] = ["example/api@sha256:" + "b" * 64]
        self.after["deployments"][0]["ready"] = 1
        self.after["pods"][0]["containers"][0]["restarts"] = 4
        kinds = {f["kind"] for f in self.compare()["findings"]}
        self.assertTrue({"image-change", "replicas-change", "restarts-increased"} <= kinds)

    def test_counter_reset_is_not_a_negative_increase(self):
        self.before["pods"][0]["containers"][0]["restarts"] = 4
        findings = self.compare()["findings"]
        self.assertTrue(any(f["kind"] == "counter-reset" for f in findings))
        self.assertFalse(any(f["kind"] == "restarts-increased" for f in findings))

    def test_replaced_pod_has_no_restart_delta(self):
        self.after["pods"][0]["uid"] = "replacement"
        self.after["pods"][0]["containers"][0]["restarts"] = 4
        kinds = {f["kind"] for f in self.compare()["findings"]}
        self.assertIn("pod-replaced", kinds)
        self.assertNotIn("restarts-increased", kinds)

    def test_different_namespace_is_rejected(self):
        self.after["namespace"] = "other"
        with self.assertRaises(ValueError):
            self.compare()

    def test_time_order_is_checked(self):
        self.after["created_at"] = "2026-10-14T12:00:00+00:00"
        with self.assertRaises(ValueError):
            self.compare()

    def test_partial_snapshot_does_not_claim_deletion(self):
        self.after["pods"] = []
        self.after["pods_truncated"] = True
        report = self.compare()
        self.assertTrue(any("truncated" in warning for warning in report["warnings"]))
        self.assertEqual(report["findings"][0]["kind"], "not-captured")

    def test_new_warning_and_event_series(self):
        event = {"type": "Warning", "object": "api-1", "reason": "BackOff",
                 "count": 1, "uid": "warning-1"}
        self.after["events"] = [event]
        self.assertTrue(any(f["kind"] == "warning-first-captured"
                            for f in self.compare()["findings"]))
        self.before["events"] = [deepcopy(event)]
        self.after["events"][0]["count"] = 3
        self.assertTrue(any(f["kind"] == "warning-count-increased"
                            for f in self.compare()["findings"]))

    def test_preflight_report_is_rejected(self):
        self.after.pop("pods")
        with self.assertRaises(ValueError):
            self.compare()

    def test_cli_is_offline_and_exit_code_is_opt_in(self):
        self.after["deployments"][0]["ready"] = 1
        self.save()
        with patch("devops_toolkit.cli.subprocess.run") as process, redirect_stdout(io.StringIO()):
            self.assertEqual(main(["compare", str(self.before_path), str(self.after_path)]), 0)
            self.assertEqual(main(["compare", str(self.before_path), str(self.after_path),
                                   "--fail-on-change"]), 1)
            process.assert_not_called()

    def test_unrelated_fields_are_not_copied_into_output(self):
        self.after["annotations"] = {"token": "private-marker"}
        self.after["logs"] = ["private-marker"]
        self.after["deployments"][0]["ready"] = 1
        self.assertNotIn("private-marker", json.dumps(self.compare()))


if __name__ == "__main__":
    unittest.main()
