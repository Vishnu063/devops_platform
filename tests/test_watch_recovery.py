"""Mock-only cases for bounded automatic recovery; execution pending."""
import unittest
from unittest.mock import MagicMock, patch

from devops_toolkit.watch_recovery import monitor, failed_rollout


class WatchRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.policy = {'context': 'lab', 'namespace': 'platform', 'deployment': 'api'}
        self.deployment = {'metadata': {'generation': 2}, 'status': {
            'observedGeneration': 2, 'conditions': [
                {'type': 'Progressing', 'status': 'False', 'reason': 'ProgressDeadlineExceeded'}]}}

    def test_stale_failed_condition_does_not_trigger(self):
        self.deployment['status']['observedGeneration'] = 1
        self.assertFalse(failed_rollout(self.deployment))

    def test_preview_detects_failure_without_mutating(self):
        kube = MagicMock()
        kube.get.return_value = self.deployment
        with patch('devops_toolkit.watch_recovery.load_policy', return_value=self.policy), \
                patch('devops_toolkit.cli.Kube', return_value=kube), \
                patch('devops_toolkit.watch_recovery.plan', return_value=([], [])), \
                patch('devops_toolkit.watch_recovery.recovered', return_value=False), \
                patch('devops_toolkit.recovery.main') as repair, \
                patch('devops_toolkit.watch_recovery.time.sleep'):
            self.assertEqual(monitor('policy', failure_observations=1), 0)
        repair.assert_not_called()
        kube.run.assert_not_called()

    def test_recovery_is_invoked_once_and_failure_is_not_retried(self):
        kube = MagicMock()
        kube.get.return_value = self.deployment
        with patch('devops_toolkit.watch_recovery.load_policy', return_value=self.policy), \
                patch('devops_toolkit.cli.Kube', return_value=kube), \
                patch('devops_toolkit.watch_recovery.plan', return_value=([], [])), \
                patch('devops_toolkit.watch_recovery.recovered', return_value=False), \
                patch('devops_toolkit.recovery.main', return_value=2) as repair, \
                patch('devops_toolkit.watch_recovery.time.sleep'), \
                patch('devops_toolkit.watch_recovery.Path') as path:
            path.return_value.exists.return_value = False
            path.return_value.parent.is_dir.return_value = True
            self.assertEqual(monitor('policy', execute=True, audit='audit', failure_observations=1), 2)
        repair.assert_called_once()
        self.assertIn('expected_policy_sha256', repair.call_args.kwargs)

    def test_policy_change_stops_before_repair(self):
        with patch('devops_toolkit.watch_recovery.load_policy', side_effect=[self.policy, {**self.policy, 'context': 'other'}]), \
                patch('devops_toolkit.cli.Kube'), \
                patch('devops_toolkit.recovery.main') as repair:
            with self.assertRaises(ValueError):
                monitor('policy')
        repair.assert_not_called()

    def test_ready_rollout_exits_without_repair(self):
        kube = MagicMock()
        kube.get.return_value = self.deployment
        with patch('devops_toolkit.watch_recovery.load_policy', return_value=self.policy), \
                patch('devops_toolkit.cli.Kube', return_value=kube), \
                patch('devops_toolkit.watch_recovery.plan', return_value=([], [])), \
                patch('devops_toolkit.watch_recovery.recovered', return_value=True), \
                patch('devops_toolkit.recovery.main') as repair:
            self.assertEqual(monitor('policy'), 0)
        repair.assert_not_called()

    def test_window_timeout_does_not_repair(self):
        with patch('devops_toolkit.watch_recovery.load_policy', return_value=self.policy), \
                patch('devops_toolkit.cli.Kube'), \
                patch('devops_toolkit.watch_recovery.time.monotonic', side_effect=[0, 100]), \
                patch('devops_toolkit.recovery.main') as repair:
            self.assertEqual(monitor('policy', max_wait=30), 1)
        repair.assert_not_called()
