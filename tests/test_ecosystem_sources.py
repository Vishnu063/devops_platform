import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('liveflow',Path(__file__).resolve().parents[1]/'liveflow/server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class EcosystemSourcesTests(unittest.TestCase):
 def test_jenkins_rejects_insecure_and_credential_urls(self):
  for url in ['http://remote.example','https://user:password@example.com','https://example.com/?token=secret']:
   with self.assertRaises(ValueError):module.jenkins_resources(url,'owned-job')
 def test_native_stderr_does_not_enter_source_warning(self):
  from types import SimpleNamespace
  with patch.object(module.subprocess,'run',return_value=SimpleNamespace(returncode=1,stderr='token=PRIVATE')):
   with self.assertRaises(RuntimeError) as raised:module.run(['kubectl','get','pods'])
  self.assertNotIn('PRIVATE',str(raised.exception))
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

class PollCapacityTests(unittest.TestCase):
 def test_slow_sources_do_not_accumulate_parallel_collection_work(self):
  import threading
  args=SimpleNamespace(context=None,jenkins_url=None,jenkins_job=None)
  entered=threading.Event();release=threading.Event();collector=module.Collector(args)
  def slow():entered.set();release.wait(timeout=2);return [],[],None
  with patch.object(module,'docker_resources',side_effect=slow) as source:
   worker=threading.Thread(target=collector.snapshot);worker.start()
   try:
    self.assertTrue(entered.wait(timeout=1));self.assertTrue(collector.snapshot()['busy']);self.assertEqual(1,source.call_count)
   finally:release.set();worker.join(timeout=2)
