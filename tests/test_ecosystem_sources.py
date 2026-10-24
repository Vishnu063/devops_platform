import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('liveflow',Path(__file__).resolve().parents[1]/'liveflow/server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class EcosystemSourcesTests(unittest.TestCase):
 def test_cluster_and_incident_sources_are_optional_and_disconnected(self):
  args=SimpleNamespace(context=None,ops_pilot_url=None)
  with patch.object(module,'run') as command:
   for fn in (module.optional_cluster_sources,module.helm_resources,module.argocd_resources,module.incident_resources):
    nodes,edges,warning=fn(args);self.assertFalse(nodes);self.assertIn('disconnected',warning)
   command.assert_not_called()
 def test_argo_is_fixed_read_only_and_retains_sync_health(self):
  args=SimpleNamespace(context='owned-lab',namespace='demo',argocd_namespace='argocd')
  with patch.object(module,'run',return_value='{"items":[{"metadata":{"name":"demo"},"status":{"health":{"status":"Healthy"},"sync":{"status":"OutOfSync"}}}]}') as command:
   nodes,_,_=module.argocd_resources(args);self.assertEqual('warning',nodes[0]['status']);self.assertIn('OutOfSync',nodes[0]['detail'])
   self.assertIn('get',command.call_args.args[0]);self.assertNotIn('sync',command.call_args.args[0])
