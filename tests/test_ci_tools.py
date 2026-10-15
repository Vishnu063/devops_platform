"""Regression cases supplied for future CI; all Kubernetes/Helm calls are mocked."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from devops_toolkit import manifests
from devops_toolkit.bundle import controlled_by, collect
from devops_toolkit.drift import differences, inspect as inspect_drift
from devops_toolkit.manifest_check import inspect as inspect_manifest
from devops_toolkit.recovery import PREFIX, fingerprint
from devops_toolkit.repair_dry_run import inspect as inspect_dry_run


def deployment():
    return {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {
        'name': 'api', 'namespace': 'platform', 'uid': 'deployment-uid', 'generation': 1,
        'resourceVersion': '10', 'annotations': {PREFIX + 'allow-image-recovery': 'true'}},
        'spec': {'replicas': 1, 'selector': {'matchLabels': {'app': 'api'}},
                 'strategy': {'rollingUpdate': {'maxUnavailable': 0}},
                 'template': {'metadata': {'labels': {'app': 'api'}}, 'spec': {'containers': [
                     {'name': 'web', 'image': 'example.invalid/api@sha256:' + 'a'*64,
                      'resources': {'requests': {'cpu': '10m', 'memory': '16Mi'},
                                    'limits': {'cpu': '100m', 'memory': '64Mi'}},
                      'readinessProbe': {'tcpSocket': {'port': 8080}},
                      'livenessProbe': {'tcpSocket': {'port': 8080}}}]}}}}


class CiToolsTests(unittest.TestCase):
    def test_json_list_and_multidocument_yaml_normalize(self):
        obj = deployment()
        self.assertEqual(manifests.parse(json.dumps(obj))['items'][0], obj)
        text = 'apiVersion: v1\nkind: Service\nmetadata:\n  name: api\nspec:\n  ports:\n    - port: 80\n---\n' + json.dumps(obj)
        self.assertEqual(len(manifests.parse(text)['items']), 2)

    def test_unsafe_yaml_duplicate_keys_and_aliases_are_rejected(self):
        for text in ['!!python/object/apply:os.system ["false"]',
                     'apiVersion: v1\nkind: Service\nmetadata: {name: a, name: b}',
                     'apiVersion: v1\nkind: List\nitems: &x [*x]']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                manifests.parse(text)

    def test_helm_render_is_local_bounded_and_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'Chart.yaml').write_text('apiVersion: v2\nname: fixture\nversion: 0.1.0\n')
            args = SimpleNamespace(file=None, chart=folder, release='demo', namespace='platform', values=[], helm_set=['image.tag=fixture'])
            result = SimpleNamespace(returncode=0, stdout=json.dumps(deployment()).encode())
            with patch('devops_toolkit.manifests.subprocess.run', return_value=result) as run:
                manifests.source_document(args)
                manifests.source_document(args)
            run.assert_called_once()
            command = run.call_args.args[0]
            self.assertEqual(command[:2], ['helm', 'template'])
            self.assertNotIn('--install', command)
            self.assertNotIn('--dependency-update', command)
            self.assertEqual(run.call_args.kwargs['timeout'], 60)

    def test_offline_check_never_constructs_a_cluster_client(self):
        with patch('devops_toolkit.cli.Kube') as kube:
            report = inspect_manifest(manifests.normalize([deployment()]), 'platform')
        kube.assert_not_called()
        self.assertEqual(report['deployment_readiness'], 'NOT_ASSESSED_OFFLINE')
        self.assertEqual(report['configuration_decision'], 'CHECKS_PASSED')

    def test_offline_check_blocks_mutable_image_and_missing_probe(self):
        obj = deployment()
        container = obj['spec']['template']['spec']['containers'][0]
        container['image'] = 'api:latest'
        del container['readinessProbe']
        report = inspect_manifest(manifests.normalize([obj]), 'platform')
        self.assertEqual(report['configuration_decision'], 'BLOCKED')

    def test_drift_reports_paths_not_sensitive_values(self):
        rows = differences({'env': [{'name': 'PASSWORD', 'value': 'desired-secret'}]},
                           {'env': [{'name': 'PASSWORD', 'value': 'live-secret'}]})
        self.assertEqual(rows[0]['path'], '/env/0/value')
        self.assertNotIn('desired-secret', json.dumps(rows))
        self.assertNotIn('live-secret', json.dumps(rows))

    def test_drift_does_not_treat_server_defaults_as_extra_drift(self):
        rows = differences({'replicas': 1}, {'replicas': 1, 'revisionHistoryLimit': 10})
        self.assertEqual(rows, [])

    def test_server_dry_run_submits_flag_without_mutating_mock_live_state(self):
        obj = deployment()
        original = copy.deepcopy(obj)
        namespace = {'metadata': {'uid': 'namespace-uid'}}
        policy = {'context': 'lab', 'namespace': 'platform', 'namespace_uid': 'namespace-uid',
                  'deployment': 'api', 'deployment_uid': 'deployment-uid',
                  'failed_template_sha256': fingerprint(obj['spec']['template']),
                  'approved_images': {'web': 'example.invalid/api@sha256:' + 'b'*64},
                  'expires_at': (datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}
        kube = MagicMock()
        kube.context, kube.namespace = 'lab', 'platform'
        kube.get.side_effect = lambda kind,*a: copy.deepcopy(namespace if kind == 'namespace' else obj)
        def server(*arguments):
            self.assertIn('--dry-run=server', arguments)
            patch_ops = json.loads(arguments[arguments.index('-p')+1])
            response = copy.deepcopy(obj)
            response['spec']['template']['spec']['containers'][0]['image'] = policy['approved_images']['web']
            response['metadata']['annotations'][PREFIX+'recovery-attempt'] = patch_ops[-1]['value']
            return json.dumps(response)
        kube.run.side_effect = server
        report = inspect_dry_run(kube, policy)
        self.assertEqual(report['result'], 'SERVER_ACCEPTED')
        self.assertFalse(report['persisted_patch'])
        self.assertEqual(obj, original)
        kube.run.assert_called_once()

    def test_bundle_excludes_same_label_unrelated_pods(self):
        obj = deployment()
        rs = {'metadata': {'name': 'api-rs', 'uid': 'rs-uid', 'ownerReferences': [
            {'kind': 'Deployment', 'uid': 'deployment-uid', 'controller': True}]}}
        owned = {'metadata': {'name': 'owned', 'uid': 'pod-owned', 'ownerReferences': [
            {'kind': 'ReplicaSet', 'uid': 'rs-uid', 'controller': True}]}, 'spec': {'containers': []},
                 'status': {'phase': 'Pending'}}
        other = copy.deepcopy(owned)
        other['metadata'].update(name='unrelated', uid='pod-unrelated', ownerReferences=[])
        datasets = {'replicasets': [rs], 'pods': [owned, other], 'events': [], 'services': []}
        kube = MagicMock()
        kube.context, kube.namespace = 'lab', 'platform'
        def get(kind,*args):
            if kind == 'deployment': return obj
            if kind == 'namespace': return {'metadata': {'uid': 'ns-uid'}}
            return {'items': datasets[kind]}
        kube.get.side_effect = get
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(deployment='api', output=str(Path(folder)/'bundle'), include_logs=False, max_pods=10)
            directory, report = collect(kube, args)
            self.assertEqual([p['name'] for p in report['pods']], ['owned'])
            self.assertNotIn('unrelated', (directory/'report.json').read_text())
        kube.run.assert_not_called()

    def test_controller_ownership_is_required(self):
        obj = {'metadata': {'ownerReferences': [{'kind': 'ReplicaSet', 'uid': 'x', 'controller': False}]}}
        self.assertFalse(controlled_by(obj, 'ReplicaSet', {'x'}))
