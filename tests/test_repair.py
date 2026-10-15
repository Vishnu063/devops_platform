"""Mock-only repair cases. Test execution is deferred by project request."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from devops_toolkit.recovery import fingerprint, PREFIX
from devops_toolkit.repair import plan, load_policy, monitor, service_ready


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.obj = {'kind': 'Deployment', 'metadata': {'uid': 'uid', 'name': 'api',
                    'namespace': 'platform', 'generation': 2, 'resourceVersion': '7',
                    'annotations': {PREFIX + 'allow-repair': 'true'}},
                    'spec': {'replicas': 1, 'template': {'spec': {'containers': [
                        {'name': 'api', 'image': 'registry/api@sha256:' + 'a'*64}]}}},
                    'status': {'observedGeneration': 2, 'conditions': [
                        {'type': 'Progressing', 'status': 'False', 'reason': 'ProgressDeadlineExceeded'}]}}
        self.ns = {'metadata': {'uid': 'ns'}}
        self.p = {'context': 'lab', 'namespace': 'platform', 'namespace_uid': 'ns',
                  'kind': 'Deployment', 'name': 'api', 'uid': 'uid',
                  'failed_spec_sha256': fingerprint(self.obj['spec']),
                  'expires_at': (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                  'action': 'containers', 'approved': {'api': {'resources': {'limits': {'memory': '256Mi'}}}}}

    def test_container_restoration_preserves_other_fields_and_has_atomic_latch(self):
        patch_ops, desired = plan(self.obj, self.ns, self.p, [])
        self.assertEqual(patch_ops[1]['path'], '/metadata/resourceVersion')
        self.assertEqual(patch_ops[-1]['path'], '/metadata/annotations/devops-platform.io~1repair-attempt')
        self.assertEqual(desired['template']['spec']['containers'][0]['image'], self.obj['spec']['template']['spec']['containers'][0]['image'])
        self.assertNotIn('resources', self.obj['spec']['template']['spec']['containers'][0])

    def test_identity_hash_optin_latch_and_gitops_are_enforced(self):
        for key, value in [('uid', 'other'), ('failed_spec_sha256', '0'*64), ('namespace_uid', 'other')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                plan(self.obj, self.ns, {**self.p, key: value}, [])
        for key, value in [(PREFIX+'repair-attempt', 'old'), ('argocd.argoproj.io/tracking-id', 'app'),
                           (PREFIX+'allow-repair', 'false')]:
            d=copy.deepcopy(self.obj); d['metadata']['annotations'][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                plan(d, self.ns, self.p, [])

    def test_failure_must_belong_to_observed_generation(self):
        self.obj['status']['observedGeneration'] = 1
        with self.assertRaises(ValueError):
            plan(self.obj, self.ns, self.p, [])

    def test_replica_repair_refuses_hpa_zero_and_downscale(self):
        p={**self.p, 'action': 'replicas', 'approved': 2}
        ops, desired=plan(self.obj,self.ns,p,[])
        self.assertEqual(desired['replicas'],2)
        with self.assertRaises(ValueError):
            plan(self.obj,self.ns,p,[{'spec':{'scaleTargetRef':{'kind':'Deployment','name':'api'}}}])
        for replicas in [0,2,3]:
            self.obj['spec']['replicas']=replicas
            with self.assertRaises(ValueError):
                plan(self.obj,self.ns,{**p,'failed_spec_sha256':fingerprint(self.obj['spec'])},[])

    def test_service_readiness_requires_owned_nonterminating_ready_endpoint(self):
        kube=MagicMock(); slice_={'metadata':{'ownerReferences':[{'kind':'Service','uid':'uid'}]},
                                'endpoints':[{'addresses':['10.0.0.1'],'conditions':{'ready':True}}]}
        kube.get.return_value={'items':[slice_]}
        self.assertTrue(service_ready(kube,self.obj))
        slice_['endpoints'][0]['conditions']['terminating']=True
        self.assertFalse(service_ready(kube,self.obj))
        slice_['endpoints'][0]['conditions']['terminating']=False
        slice_['metadata']['ownerReferences'][0]['uid']='other'
        self.assertFalse(service_ready(kube,self.obj))

    def test_service_selector_patch_refuses_exposed_or_notready_service(self):
        self.obj['kind']='Service'; self.obj['spec']={'type':'ClusterIP','selector':{'app':'wrong'}}
        p={**self.p,'kind':'Service','action':'selector','approved':{'app':'api'},'failed_spec_sha256':fingerprint(self.obj['spec'])}
        _, desired=plan(self.obj,self.ns,p,[])
        self.assertEqual(desired['selector'],{'app':'api'})
        self.obj['spec']['publishNotReadyAddresses']=True
        p['failed_spec_sha256']=fingerprint(self.obj['spec'])
        with self.assertRaises(ValueError):
            plan(self.obj,self.ns,p,[])

    def test_loader_rejects_plaintext_env_unpinned_image_and_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'policy.json'
            for changes in [
                {'approved':{'api':{'env':[{'name':'PASSWORD','value':'sensitive'}]}}},
                {'approved':{'api':{'image':'api:latest'}}},
                {'expires_at':'2000-01-01T00:00:00Z'},
                {'action':'replicas','approved':11}]:
                path.write_text(json.dumps({**self.p,**changes}))
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    load_policy(path)

    def test_preview_never_patches_and_policy_edits_stop(self):
        kube=MagicMock(); kube.get.side_effect=lambda kind,*args: self.ns if kind=='namespace' else self.obj
        with patch('devops_toolkit.repair.load_policy',return_value=self.p), patch('devops_toolkit.cli.Kube',return_value=kube), patch('devops_toolkit.repair.time.sleep'):
            self.assertEqual(monitor('unused'),0)
        kube.run.assert_not_called()
        with patch('devops_toolkit.repair.load_policy',side_effect=[self.p,{**self.p,'context':'other'}]), patch('devops_toolkit.cli.Kube',return_value=kube):
            with self.assertRaises(ValueError):
                monitor('unused')
        kube.run.assert_not_called()

    def test_unknown_patch_outcome_is_audited_and_never_retried(self):
        from devops_toolkit.cli import QueryError
        kube=MagicMock(); kube.get.side_effect=lambda kind,*args: self.ns if kind=='namespace' else self.obj
        kube.run.side_effect=QueryError('untrusted error')
        with tempfile.TemporaryDirectory() as directory:
            audit=str(Path(directory)/'audit.jsonl')
            with patch('devops_toolkit.repair.load_policy',return_value=self.p), patch('devops_toolkit.cli.Kube',return_value=kube), patch('devops_toolkit.repair.time.sleep'):
                with self.assertRaises(QueryError):
                    monitor('unused',execute=True,audit=audit)
            self.assertIn('outcome_unknown',Path(audit).read_text())
            self.assertEqual(Path(audit).stat().st_mode & 0o777,0o600)
        kube.run.assert_called_once()
