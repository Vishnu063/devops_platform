"""Offline regression cases for onboarding/export boundaries. Supplied, not run."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from devops_toolkit import doctor, example, explain, gitops_propose, guide, report


class UsabilityTests(unittest.TestCase):
    def test_doctor_default_never_queries_cluster_or_runs_tools(self):
        with patch('devops_toolkit.cli.Kube') as kube, patch('subprocess.run') as run:
            result = doctor.inspect('offline')
        kube.assert_not_called()
        run.assert_not_called()
        self.assertEqual(result['kind'], 'doctor')

    def test_guide_only_plans_and_shell_quotes(self):
        command = guide.plan('diagnose', {'CONTEXT': 'work; echo bad', 'NAMESPACE': 'platform'})
        self.assertEqual(command[command.index('--context') + 1], 'work; echo bad')
        with patch('sys.stdin.isatty', return_value=False), patch('builtins.input') as prompt:
            self.assertEqual(guide.main([]), 2)
        prompt.assert_not_called()

    def test_html_escapes_evidence_and_has_no_external_resources(self):
        document = example.fixture('crash')
        document['findings'][0]['signal'] = '<script>alert(1)</script>'
        document['logs'] = [{'text': 'DO_NOT_EXPORT'}]
        rendered = report.html(report.summarize(document))
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertNotIn('DO_NOT_EXPORT', rendered)
        self.assertIn("default-src 'none'", rendered)
        self.assertIn('ILLUSTRATIVE', rendered)

    def test_handover_does_not_invent_impact_or_resolution(self):
        text = report.markdown(report.summarize(example.fixture('image')), handover=True)
        self.assertIn('NOT ASSESSED', text)
        self.assertIn('TO COMPLETE', text)
        self.assertIn('ILLUSTRATIVE', text)

    def test_export_refuses_overwrite_and_unknown_schema(self):
        with tempfile.TemporaryDirectory() as root:
            source, output = Path(root)/'source.json', Path(root)/'report.html'
            source.write_text(json.dumps(example.fixture('crash')))
            output.write_text('preserve')
            self.assertEqual(report.main([str(source), '--output', str(output)]), 2)
            self.assertEqual(output.read_text(), 'preserve')
            source.write_text('{"schema_version": 1, "kind": "arbitrary"}')
            with self.assertRaises(ValueError):
                report.load(source)

    def test_next_read_uses_only_explicit_scope_and_known_resource(self):
        finding = {'resource': 'pods/api', 'signal': 'CrashLoopBackOff'}
        advice = explain.next_step({'context': 'my-context', 'namespace': 'platform'}, finding)
        self.assertIn('--context my-context', advice['read_only_command'])
        self.assertIsNone(explain.next_step({}, finding)['read_only_command'])
        self.assertIsNone(explain.next_step({'context': 'c', 'namespace': 'n'}, {'resource': 'secrets/key'})['read_only_command'])

    def source(self, digest='1', replicas=2):
        return json.dumps({'apiVersion': 'apps/v1', 'kind': 'Deployment',
                           'metadata': {'name': 'api'}, 'spec': {'replicas': replicas,
                           'template': {'spec': {'containers': [{'name': 'api',
                           'image': 'example.invalid/api@sha256:' + digest * 64}]}}}}, indent=2) + '\n'

    def test_gitops_proposal_contains_only_image_changes(self):
        with patch('subprocess.run') as run:
            text, changes = gitops_propose.proposal(self.source(), self.source('2'), 'apps/api.json', 'platform')
        run.assert_not_called()
        self.assertIn('@@', text)
        self.assertIn('sha256:' + '2'*64, text)
        self.assertNotIn('replicas', text)
        self.assertEqual(changes[0]['deployment'], 'api')

    def test_gitops_refuses_unrelated_edits_and_unsafe_paths(self):
        with self.assertRaises(ValueError):
            gitops_propose.proposal(self.source(), self.source('2', replicas=0), 'apps/api.json', 'platform')
        with self.assertRaises(ValueError):
            gitops_propose.proposal(self.source(), self.source('2'), '../api.json', 'platform')
        with self.assertRaises(ValueError):
            gitops_propose.proposal(self.source(), self.source(), 'apps/api.json', 'platform')

    def test_comparison_values_and_extra_fields_are_not_exported(self):
        summary = report.summarize({'schema_version': 1, 'command': 'compare',
                                   'findings': [{'resource': 'deployment/api', 'message': 'Image changed',
                                                 'before': 'PRIVATE_OLD', 'after': 'PRIVATE_NEW'}],
                                   'arbitrary': 'PRIVATE_EXTRA'})
        text = json.dumps(summary)
        for value in ['PRIVATE_OLD', 'PRIVATE_NEW', 'PRIVATE_EXTRA']:
            self.assertNotIn(value, text)

    def test_dry_run_report_does_not_claim_recovery(self):
        summary = report.summarize({'schema_version': 1, 'kind': 'repair-dry-run',
                                   'result': 'SERVER_ACCEPTED', 'target': 'Deployment/api'})
        self.assertIn('no persistent patch', summary['rows'][0]['evidence'])
        self.assertIn('separate explicit command', summary['rows'][0]['next_step'])


if __name__ == '__main__':
    unittest.main()
