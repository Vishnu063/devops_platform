"""Offline regression cases supplied for later execution; no real cluster/webhook."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from devops_toolkit import alerts
from devops_toolkit.controls import ensure_enabled
from devops_toolkit.policy import build_policy
from devops_toolkit.release_check import availability, decision, service_checks, unavailable_count
from devops_toolkit.timeline import build


class ProductTests(unittest.TestCase):
    def deployment(self):
        return {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {
            'name': 'api', 'namespace': 'platform', 'uid': 'dep-uid', 'generation': 2,
            'resourceVersion': '10', 'annotations': {'devops-platform.io/allow-image-recovery': 'true'}},
            'spec': {'replicas': 2, 'selector': {'matchLabels': {'app': 'api'}},
                     'template': {'metadata': {'labels': {'app': 'api'}}, 'spec': {'containers': [
                         {'name': 'web', 'image': 'registry/api@sha256:' + 'a'*64,
                          'ports': [{'name': 'http', 'containerPort': 8080}],
                          'readinessProbe': {'httpGet': {'port': 'http', 'path': '/'}}}]}}},
            'status': {'observedGeneration': 2, 'availableReplicas': 2}}

    def test_policy_generator_reads_ids_and_hash_without_mutation(self):
        obj = self.deployment()
        kube = MagicMock()
        kube.context, kube.namespace = 'lab', 'platform'
        kube.get.side_effect = lambda kind, name: {'metadata': {'name': 'platform', 'uid': 'ns-uid'}} if kind == 'namespace' else obj
        approved = {'web': 'registry/api@sha256:' + 'b'*64}
        policy = build_policy(kube, 'api', 'Deployment', 'images', approved)
        self.assertEqual(policy['deployment_uid'], 'dep-uid')
        self.assertEqual(policy['namespace_uid'], 'ns-uid')
        self.assertEqual(len(policy['failed_template_sha256']), 64)
        self.assertEqual(policy['approved_images'], approved)
        kube.run.assert_not_called()

    def test_service_selector_and_named_port_failures_are_detected(self):
        service = {'metadata': {'name': 'api'}, 'spec': {
            'selector': {'app': 'wrong'}, 'ports': [{'port': 80, 'targetPort': 'missing'}]}}
        self.assertEqual([c['status'] for c in service_checks(service, self.deployment())], ['FAIL', 'FAIL'])
        service['spec']['selector'] = {'app': 'api'}
        service['spec']['ports'][0]['targetPort'] = 'http'
        self.assertTrue(all(c['status'] == 'PASS' for c in service_checks(service, self.deployment())))

    def test_availability_flags_downscale_recreate_and_immutable_selector(self):
        live = self.deployment()
        candidate = copy.deepcopy(live)
        candidate['spec']['replicas'] = 1
        candidate['spec']['strategy'] = {'type': 'Recreate'}
        candidate['spec']['selector'] = {'matchLabels': {'app': 'other'}}
        checks = availability(candidate, live)
        self.assertEqual(decision(checks), 'BLOCKED')
        self.assertGreaterEqual(sum(c['status'] == 'WARN' for c in checks), 2)
        self.assertEqual(unavailable_count('25%', 3), 0)
        self.assertEqual(unavailable_count('25%', 4), 1)

    def test_unknown_or_skipped_evidence_never_passes(self):
        self.assertEqual(decision([{'status': 'UNKNOWN'}]), 'NEEDS_REVIEW')
        self.assertEqual(decision([{'status': 'WARN'}]), 'NEEDS_REVIEW')
        self.assertEqual(decision([{'status': 'PASS'}, {'status': 'NOTE'}]), 'CHECKS_PASSED')

    def test_namespace_pause_and_environment_stop_fail_closed(self):
        namespace = {'metadata': {'uid': 'ns', 'annotations': {'devops-platform.io/repairs-paused': 'true'}}}
        with self.assertRaises(ValueError):
            ensure_enabled(namespace, 'ns')
        namespace['metadata']['annotations'] = {}
        with patch.dict('os.environ', {'DEVOPS_TOOLKIT_DISABLE_REPAIRS': '1'}):
            with self.assertRaises(ValueError):
                ensure_enabled(namespace, 'ns')
        with self.assertRaises(ValueError):
            ensure_enabled(namespace, 'wrong')

    def test_alert_failure_does_not_retry_operation(self):
        runner = MagicMock(return_value=0)
        with patch('devops_toolkit.alerts.prepare', return_value={'provider': 'webhook', 'url': 'https://example.invalid/secret'}), \
                patch('devops_toolkit.alerts.send', side_effect=ValueError('failed')):
            self.assertEqual(alerts.invoke(['diagnose', '--context', 'lab', '--notify-config', 'config'], runner), 3)
        runner.assert_called_once_with(['diagnose', '--context', 'lab'])

    def test_bad_alert_config_blocks_before_operation(self):
        runner = MagicMock()
        with patch('devops_toolkit.alerts.prepare', side_effect=ValueError('bad')):
            self.assertEqual(alerts.invoke(['repair', '--policy', 'p', '--notify-config', 'bad'], runner), 2)
        runner.assert_not_called()

    def test_alert_payload_omits_sensitive_fields(self):
        event = {'event_id': 'id', 'time': 'now', 'tool': 'tool', 'command': 'repair',
                 'result': 'recovery_succeeded', 'exit_code': 0, 'secret': 'do-not-send', 'policy': 'private'}
        response = MagicMock()
        response.__enter__.return_value.status = 200
        opener = MagicMock()
        opener.open.return_value = response
        with patch('devops_toolkit.alerts.urllib.request.build_opener', return_value=opener):
            alerts.send({'provider': 'webhook', 'url': 'https://example.invalid/secret'}, event)
        payload = json.loads(opener.open.call_args.args[0].data)
        self.assertNotIn('secret', payload)
        self.assertNotIn('policy', payload)
        self.assertEqual(payload['result'], 'recovery_succeeded')

    def test_timeline_correlates_scope_and_does_not_copy_arbitrary_audit_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base = {'schema_version': 1, 'context': 'lab', 'namespace': 'platform',
                    'created_at': '2026-10-15T10:00:00+00:00', 'pods': [], 'deployments': [], 'events': []}
            (root/'before.json').write_text(json.dumps(base))
            (root/'after.json').write_text(json.dumps({**base, 'created_at': '2026-10-15T10:02:00+00:00'}))
            records = [{'time': '2026-10-15T10:01:00+00:00', 'event': 'intent', 'context': 'lab',
                        'namespace': 'platform', 'action': 'images', 'secret': 'do-not-copy'},
                       {'time': '2026-10-15T10:01:30+00:00', 'event': 'deployment_ready'}]
            (root/'audit.jsonl').write_text('\n'.join(json.dumps(r) for r in records))
            report = build([root/'after.json', root/'before.json'], [root/'audit.jsonl'])
            self.assertEqual(report['entries'][1]['event'], 'intent')
            self.assertNotIn('do-not-copy', json.dumps(report))
            records[0]['namespace'] = 'other'
            (root/'audit.jsonl').write_text('\n'.join(json.dumps(r) for r in records))
            with self.assertRaises(ValueError):
                build([root/'before.json'], [root/'audit.jsonl'])

    def test_template_only_change_is_observable_without_copying_values(self):
        from devops_toolkit.compare import compare_files
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            deployment = {'name': 'api', 'desired': 1, 'ready': 1, 'updated': 1, 'images': [], 'template_sha256': 'a'*64}
            before = {'schema_version': 1, 'context': 'lab', 'namespace': 'platform',
                      'created_at': '2026-10-15T10:00:00+00:00', 'pods': [], 'events': [], 'deployments': [deployment]}
            after = copy.deepcopy(before)
            after['created_at'] = '2026-10-15T10:01:00+00:00'
            after['deployments'][0]['template_sha256'] = 'b'*64
            (root/'before.json').write_text(json.dumps(before))
            (root/'after.json').write_text(json.dumps(after))
            report = compare_files(root/'before.json', root/'after.json')
            self.assertIn('pod-template-changed', [f['kind'] for f in report['findings']])
