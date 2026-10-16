"""Offline demo guard checks. No real Docker or Kubernetes calls."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from devops_toolkit import demo
from devops_toolkit.recovery import fingerprint


class DemoTests(unittest.TestCase):
    def test_selector_observation_handles_null_and_converging_endpoint_lists(self):
        target = {'spec': {'selector': {'app': 'wrong-demo-selector'}}}
        self.assertTrue(demo.selector_fault_observed(target, [{'endpoints': None}]))
        self.assertTrue(demo.selector_fault_observed(target, [{'endpoints': []}]))
        self.assertFalse(demo.selector_fault_observed(target, [{'endpoints': [{'conditions': {'ready': True}}]}]))
        self.assertFalse(demo.selector_fault_observed({'spec': {'selector': {'app': demo.APP}}}, []))

    def test_manifest_is_isolated_and_opts_in_only_demo_deployment(self):
        objects = demo.manifests()['items']
        namespace, deployment, service = objects
        self.assertEqual(namespace['metadata']['name'], 'devops-demo')
        self.assertEqual(deployment['metadata']['namespace'], namespace['metadata']['name'])
        self.assertEqual(service['spec']['selector'], deployment['spec']['selector']['matchLabels'])
        container = deployment['spec']['template']['spec']['containers'][0]
        self.assertIn('@sha256:', container['image'])
        self.assertTrue(container['securityContext']['readOnlyRootFilesystem'])
        self.assertFalse(deployment['spec']['template']['spec']['automountServiceAccountToken'])
        self.assertEqual(deployment['metadata']['annotations'][demo.PREFIX + 'allow-image-recovery'], 'true')

    def test_policy_binds_live_ids_and_failed_template_not_the_healthy_template(self):
        deployment = demo.manifests(demo.BAD_IMAGE)['items'][1]
        deployment['metadata']['uid'] = 'deployment-live-uid'
        policy = demo.policy_for(deployment, {'metadata': {'uid': 'namespace-live-uid'}}, 'kind-new-demo')
        self.assertEqual(policy['failed_template_sha256'], fingerprint(deployment['spec']['template']))
        self.assertEqual(policy['namespace_uid'], 'namespace-live-uid')
        self.assertEqual(policy['deployment_uid'], 'deployment-live-uid')
        self.assertEqual(policy['approved_images']['web'], demo.GOOD_IMAGE)
        self.assertGreater(datetime.fromisoformat(policy['expires_at']), datetime.now(timezone.utc))

    def test_missing_prerequisites_do_not_create_evidence_or_run_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / 'must-not-exist')
            with patch('devops_toolkit.demo.shutil.which', return_value=None), \
                    patch('devops_toolkit.demo.subprocess.run') as run:
                self.assertEqual(demo.main(['--output', output]), 2)
            self.assertFalse(Path(output).exists())
            run.assert_not_called()

    def test_existing_output_is_not_overwritten_and_no_cluster_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'marker'
            marker.write_text('preserve me')
            with patch('devops_toolkit.demo.prerequisites'), \
                    patch('devops_toolkit.demo.subprocess.run') as run:
                self.assertEqual(demo.main(['--output', directory]), 2)
            self.assertEqual(marker.read_text(), 'preserve me')
            run.assert_not_called()

    def test_failure_summary_does_not_claim_all_checks_passed(self):
        report = {'result': 'FAIL', 'stages': [{'stage': 'create local cluster', 'status': 'FAIL'}]}
        text = demo.summary(report)
        self.assertIn('**FAIL**', text)
        self.assertIn('Only stages marked PASS were observed', text)
        self.assertNotIn('**PASS**', text)
