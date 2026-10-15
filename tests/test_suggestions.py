"""Offline suggestion regression cases. Supplied; not executed in this update."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from devops_toolkit import suggest, report


class SuggestionTests(unittest.TestCase):
    def test_specific_symptoms_and_unknown_remain_distinct(self):
        self.assertEqual(suggest.topic_for('api:state:CrashLoopBackOff'), 'crash')
        self.assertEqual(suggest.topic_for('api:state:ImagePullBackOff'), 'image')
        self.assertEqual(suggest.topic_for('api:lastState:OOMKilled'), 'memory')
        self.assertEqual(suggest.topic_for('FailedMount'), 'storage')
        self.assertEqual(suggest.topic_for('PVC:Pending'), 'storage')
        self.assertEqual(suggest.topic_for('deployment-selector'), 'unknown')
        self.assertEqual(suggest.topic_for('unrecognized custom symptom'), 'unknown')
        self.assertEqual(suggest.topic_for('BackOff'), 'unknown')

    def test_only_problem_checks_are_selected(self):
        result = suggest.from_report({'checks': [{'status': 'PASS', 'check': 'image:api'},
                                                {'status': 'FAIL', 'check': 'readinessProbe:api'}]})
        self.assertEqual(result, ['probe'])
        self.assertEqual(suggest.from_report({'findings': []}), ['unknown'])

    def test_unavailable_data_does_not_prove_permissions_failure(self):
        self.assertEqual(suggest.from_report({'unavailable': ['pods']}), ['toolkit-error'])

    def test_unknown_recovery_outcome_requires_inspection(self):
        result = suggest.build(['recovery'])
        self.assertIn('never clear the latch', ' '.join(result['suggestions'][0]['steps']))
        self.assertIn('unknown', ' '.join(result['limitations']))

    def test_report_processed_offline_and_raw_values_not_copied(self):
        with tempfile.TemporaryDirectory() as root:
            source, output = Path(root)/'input.json', Path(root)/'suggestions.json'
            source.write_text(json.dumps({'schema_version': 1, 'kind': 'diagnosis', 'example': True,
                                          'findings': [{'signal': 'CrashLoopBackOff', 'secret': 'PRIVATE_VALUE'}]}))
            with patch('subprocess.run') as run, patch('devops_toolkit.cli.Kube') as kube:
                self.assertEqual(suggest.main(['--report', str(source), '--output', str(output)]), 0)
            run.assert_not_called()
            kube.assert_not_called()
            text = output.read_text()
            self.assertNotIn('PRIVATE_VALUE', text)
            self.assertTrue(json.loads(text)['example'])
            self.assertEqual(report.load(output)['kind'], 'troubleshooting-suggestions')

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)/'keep.json'
            output.write_text('preserve')
            self.assertEqual(suggest.main(['--issue', 'stuck', '--output', str(output)]), 2)
            self.assertEqual(output.read_text(), 'preserve')

    def test_hint_does_not_claim_report_exists_or_retry_mutation(self):
        hint = suggest.failure_hint(['diagnose', '--output', 'report.json'], 2)
        self.assertIn('If a JSON report was saved', hint)
        self.assertIn('suggest --report', hint)
        recovery = suggest.failure_hint(['repair', '--execute'], 2)
        self.assertIn('suggest --issue recovery', recovery)
        self.assertNotIn('--execute', recovery)
        self.assertIsNone(suggest.failure_hint(['diagnose'], 0))
        self.assertIsNone(suggest.failure_hint(['suggest'], 2))

    def test_export_contains_verification_and_uncertainty(self):
        summary = report.summarize(suggest.build(['service']))
        self.assertIn('Verify:', summary['rows'][0]['next_step'])
        self.assertIn('not proven root causes', ' '.join(summary['warnings']))


if __name__ == '__main__':
    unittest.main()
