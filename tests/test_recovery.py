"""Mock-only recovery checks; no cluster access. Execution remains pending."""
import copy
import unittest
from devops_toolkit.recovery import fingerprint, plan, recovered
from devops_toolkit.diagnose import findings_for


class RecoveryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.deployment = {
            "metadata": {"uid": "deployment-uid", "name": "api", "namespace": "platform",
                         "generation": 4, "resourceVersion": "123",
                         "annotations": {"devops-platform.io/allow-image-recovery": "true"}},
            "spec": {"replicas": 2, "template": {"spec": {"containers": [
                {"name": "api", "image": "registry/api@sha256:" + "a" * 64}]}}},
            "status": {"observedGeneration": 4, "conditions": [
                {"type": "Progressing", "status": "False", "reason": "ProgressDeadlineExceeded"}]}}
        self.namespace = {"metadata": {"uid": "namespace-uid"}}
        self.policy = {"deployment_uid": "deployment-uid", "namespace_uid": "namespace-uid",
                       "deployment": "api", "namespace": "platform",
                       "failed_template_sha256": fingerprint(self.deployment["spec"]["template"]),
                       "approved_images": {"api": "registry/api@sha256:" + "b" * 64}}

    def test_patch_is_conditional_and_only_changes_images_and_latch(self):
        patch, changes = plan(self.deployment, self.namespace, self.policy)
        self.assertEqual([op["op"] for op in patch], ["test", "test", "replace", "add"])
        self.assertEqual(patch[1]["path"], "/metadata/resourceVersion")
        self.assertEqual(patch[2]["path"], "/spec/template/spec/containers/0/image")
        self.assertEqual(changes[0]["after"], self.policy["approved_images"]["api"])

    def test_refuses_scope_changes_and_stale_template(self):
        for field in ("namespace_uid", "deployment_uid", "failed_template_sha256", "namespace", "deployment"):
            with self.subTest(field=field):
                policy = {**self.policy, field: "wrong"}
                with self.assertRaises(ValueError):
                    plan(self.deployment, self.namespace, policy)

    def test_refuses_repeated_attempt_and_gitops(self):
        for key, value in (("devops-platform.io/recovery-attempt", "previous"),
                           ("argocd.argoproj.io/tracking-id", "app")):
            d = copy.deepcopy(self.deployment)
            d["metadata"]["annotations"][key] = value
            with self.assertRaises(ValueError):
                plan(d, self.namespace, self.policy)

    def test_refuses_unobserved_or_healthy_or_unapproved(self):
        variants = []
        d = copy.deepcopy(self.deployment)
        d["status"]["observedGeneration"] = 3
        variants.append(d)
        d = copy.deepcopy(self.deployment)
        d["status"]["conditions"] = []
        variants.append(d)
        d = copy.deepcopy(self.deployment)
        d["metadata"]["annotations"] = {}
        variants.append(d)
        d = copy.deepcopy(self.deployment)
        d["spec"]["paused"] = True
        variants.append(d)
        for d in variants:
            with self.assertRaises(ValueError):
                plan(d, self.namespace, self.policy)

    def test_verification_needs_all_replicas_and_detects_concurrent_change(self):
        current = copy.deepcopy(self.deployment)
        self.assertFalse(recovered(current, self.deployment))
        current["status"].update(replicas=2, updatedReplicas=2, readyReplicas=2, availableReplicas=2)
        self.assertTrue(recovered(current, self.deployment))
        current["spec"]["replicas"] = 3
        with self.assertRaises(ValueError):
            recovered(current, self.deployment)

    def test_diagnosis_preserves_signal_without_leaking_event_messages(self):
        findings = findings_for("events", [{"metadata": {"name": "event"}, "type": "Warning",
                                          "reason": "FailedMount", "message": "secret-password"}])
        self.assertEqual(findings[0]["signal"], "FailedMount")
        self.assertNotIn("secret-password", str(findings))

    def test_diagnosis_detects_init_container_oom(self):
        findings = findings_for("pods", [{"metadata": {"name": "pod"}, "status": {
            "initContainerStatuses": [{"name": "init", "lastState": {"terminated": {"reason": "OOMKilled"}}}]}}])
        self.assertIn("OOMKilled", findings[0]["signal"])


class RecoveryExecutionTests(unittest.TestCase):
    def test_preview_never_mutates(self):
        from unittest.mock import patch, MagicMock
        from devops_toolkit.recovery import main
        kube = MagicMock()
        with patch('devops_toolkit.recovery.load_policy', return_value={
                'context': 'lab', 'namespace': 'platform', 'deployment': 'api'}), \
                patch('devops_toolkit.cli.Kube', return_value=kube), \
                patch('devops_toolkit.recovery.plan', return_value=([], [])):
            self.assertEqual(main(['--policy', 'unused']), 0)
        kube.run.assert_not_called()

    def test_missing_audit_prevents_mutation(self):
        from unittest.mock import patch, MagicMock
        from devops_toolkit.recovery import main
        kube = MagicMock()
        with patch('devops_toolkit.recovery.load_policy', return_value={
                'context': 'lab', 'namespace': 'platform', 'deployment': 'api'}), \
                patch('devops_toolkit.cli.Kube', return_value=kube), \
                patch('devops_toolkit.recovery.plan', return_value=([], [])):
            self.assertEqual(main(['--policy', 'unused', '--execute']), 2)
        kube.run.assert_not_called()
