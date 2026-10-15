"""Offline, allowlisted evidence views for humans and integrations."""
import argparse
from html import escape
import json
from pathlib import Path
import re
import sys

from .explain import next_step

SUPPORTED = {'diagnosis', 'release-check', 'offline-manifest-check', 'incident-timeline',
             'drift-report', 'repair-dry-run', 'workload-bundle', 'doctor', 'troubleshooting-suggestions'}


def clean(value):
    from .cli import redact
    if not isinstance(value, (str, int, float, bool)) and value is not None:
        return '[structured value omitted]'
    text = str(value) if value is not None else ''
    return re.sub(r'[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]', ' ', redact(text))[:2000]


def load(path):
    with Path(path).open('rb') as stream:
        data = stream.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError('Report exceeds input limit')
    document = json.loads(data)
    if not isinstance(document, dict) or type(document.get('schema_version')) is not int or document['schema_version'] != 1:
        raise ValueError('Unsupported report schema')
    snapshot = all(key in document for key in ['pods', 'deployments', 'events'])
    if snapshot:
        from .compare import load_snapshot
        return load_snapshot(path)[0]
    if document.get('kind') not in SUPPORTED and document.get('command') != 'compare' and not (
            'checks' in document and 'deployment' in document):
        raise ValueError('Unsupported report type')
    return document


def summarize(document):
    rows, warnings = [], []
    kind = document.get('kind', document.get('command', 'incident' if 'pods' in document else 'preflight'))
    def add(state, target, evidence, action='', command=None):
        if len(rows) < 500:
            rows.append(dict(status=clean(state), target=clean(target), evidence=clean(evidence),
                             next_step=clean(action), read_only_command=clean(command)))
    for suggestion in document.get('suggestions', []):
        add('SUGGESTED', suggestion['topic'], 'Possible causes: ' + ' '.join(suggestion['possible_causes']),
            ' '.join(str(i) + '. ' + step for i, step in enumerate(suggestion['steps'], 1)) + ' Verify: ' + suggestion['verify'])
    for check in document.get('checks', []):
        advice = next_step(document, check)
        add(check['status'], check.get('resource', check.get('check', 'check')),
            check.get('check', '') + ': ' + check.get('detail', ''),
            advice['next_step'] + ' More help: ' + advice['suggestion_command'] if check['status'] != 'PASS' else 'Review the documented scope of this check.')
    for finding in document.get('findings', []):
        advice = next_step(document, finding)
        evidence = finding.get('signal', finding.get('message', 'Observed change'))
        # Values from a comparison are intentionally not copied to handover exports.
        add('OBSERVED', finding.get('resource', ''), evidence, advice['next_step'] + ' More help: ' + advice['suggestion_command'], advice['read_only_command'])
    for entry in document.get('entries', []):
        add(entry.get('event', entry['source']), entry['time'], entry['summary'],
            'Correlated observation; review approved action: ' + str(entry.get('action', 'none recorded')))
    for resource in document.get('resources', []):
        for field in resource.get('fields', []):
            add('DRIFT', resource['resource'], field['path'] + ': ' + field['change'],
                'Review the desired Git source and API defaults before changing state.')
        if resource.get('truncated'):
            warnings.append('Drift records were truncated in the source report.')
    for deployment in document.get('deployments', []):
        add('OBSERVED', 'Deployment/' + deployment['name'],
            'Desired/ready/updated replicas: ' + '/'.join(str(deployment.get(k, 0)) for k in ['desired', 'ready', 'updated']),
            'Readiness counts are an observation; verify application traffic separately.')
    for pod in document.get('pods', []):
        for container in pod.get('containers', []):
            add('OBSERVED', 'Pod/' + pod['name'] + '/' + container['name'],
                'Phase: ' + str(pod.get('phase')) + '; ready: ' + str(container.get('ready')) +
                '; restarts: ' + str(container.get('restarts', 0)) + '; reason: ' + str(container.get('reason')),
                'Inspect the workload status and known dependencies; this is not a root-cause conclusion.')
    for event in document.get('events', []):
        if event.get('type') == 'Warning':
            add('WARNING', event.get('object'), event.get('reason'), 'Review this warning locally; messages are excluded.')
    if kind == 'repair-dry-run':
        add(document.get('result'), document.get('target'), 'Server validation only; no persistent patch requested.',
            'Execution requires a separate explicit command and fresh policy/live checks.')
    for key in ['limitations', 'warnings']:
        warnings.extend(clean(w) for w in document.get(key, []))
    for key in ['unavailable', 'unsupported']:
        if document.get(key):
            warnings.append('Source collection has ' + key + ' data; inspect the private original report. Conclusions are partial.')
    if document.get('pods_truncated') or any(document.get(k + '_count', len(document.get(k + 's', []))) > len(document.get(k + 's', [])) for k in ['deployment', 'event']):
        warnings.append('Source snapshot is truncated; absence is not proof of health or deletion.')
    if len(rows) == 500:
        warnings.append('Display capped at 500 rows. Consult the original report for additional evidence.')
    warnings.extend(['Evidence does not prove root cause, incident resolution or business recovery.',
                     'Review before sharing: internal names remain visible and redaction is best effort. Logs, arbitrary specs and comparison values are excluded.'])
    if document.get('example'):
        warnings.insert(0, 'ILLUSTRATIVE EXAMPLE: fabricated observations, not evidence from a real cluster.')
    return {'schema_version': 1, 'kind': 'evidence-summary', 'source_kind': clean(kind),
            'example': bool(document.get('example')), 'context': clean(document.get('context')),
            'namespace': clean(document.get('namespace')), 'observed_at': clean(document.get('created_at', document.get('after_time'))),
            'decision': clean(document.get('decision', document.get('configuration_decision', document.get('result', 'NOT ASSESSED')))),
            'rows': rows, 'warnings': list(dict.fromkeys(warnings))}


def markdown(summary, handover=False):
    def md(value):
        return re.sub(r'([\\`*_{}\[\]()|#!])', r'\\\1', escape(clean(value)))
    lines = ['# ' + ('Incident handover draft' if handover else 'Evidence report'), '',
             'Source: ' + md(summary['source_kind']), '',
             'Context: ' + md(summary['context']) + ' | Namespace: ' + md(summary['namespace']), '',
             'Observed at: ' + md(summary['observed_at']), '', 'Decision: **' + md(summary['decision']) + '**', '']
    if handover:
        lines += ['Owner: TO COMPLETE', '', 'User impact: NOT ASSESSED — engineer to complete', '',
                  'Next update time: TO COMPLETE', '', 'Recovery outcome: verify the scoped audit and application checks; do not infer from missing findings.', '']
    lines += ['| State | Target | Evidence | Next step |', '| --- | --- | --- | --- |']
    for row in summary['rows']:
        action = row['next_step'] + (' Suggested read: ' + row['read_only_command'] if row['read_only_command'] else '')
        lines.append('| ' + ' | '.join(md(v) for v in [row['status'], row['target'], row['evidence'], action]) + ' |')
    lines += ['', '## Limits and incomplete evidence', '', *['- ' + md(w) for w in summary['warnings']], '']
    return '\n'.join(lines)


def html(summary):
    e = lambda value: escape(clean(value), quote=True)
    rows = ''.join('<tr>' + ''.join('<td>' + e(row[k]) + '</td>' for k in ['status', 'target', 'evidence']) +
                   '<td>' + e(row['next_step']) + '<pre>' + e(row['read_only_command']) + '</pre></td></tr>' for row in summary['rows'])
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            '<title>DevOps evidence report</title><style>body{font:16px/1.6 system-ui;margin:2rem auto;padding:0 1rem;max-width:1100px;color:#172a3a;background:#f5f7fa}table{border-collapse:collapse;width:100%;background:white}td,th{padding:.8rem;border:1px solid #ccd4dd;text-align:left;vertical-align:top;overflow-wrap:anywhere}pre{white-space:pre-wrap}section{overflow-x:auto}h1{line-height:1.2}li{margin:.5rem 0}</style></head><body>'
            '<h1>DevOps evidence report</h1><p>Source: ' + e(summary['source_kind']) + '</p><p>Context: ' + e(summary['context']) +
            ' | Namespace: ' + e(summary['namespace']) + '</p><p>Observed: ' + e(summary['observed_at']) + '</p><p><strong>Decision: ' +
            e(summary['decision']) + '</strong></p><section><table><thead><tr><th>State</th><th>Target</th><th>Evidence</th><th>Next step</th></tr></thead><tbody>' +
            rows + '</tbody></table></section><h2>Limits and incomplete evidence</h2><ul>' +
            ''.join('<li>' + e(w) + '</li>' for w in summary['warnings']) + '</ul></body></html>\n')


def main(argv=None, handover=False):
    from .cli import write_private
    parser = argparse.ArgumentParser(prog='devops-toolkit ' + ('handover' if handover else 'report'))
    parser.add_argument('input', help='Saved toolkit JSON report; never reads adjacent logs')
    parser.add_argument('--format', choices=['html', 'markdown', 'json'], default='markdown' if handover else 'html')
    parser.add_argument('--output', required=True, help='New private file; parent must exist')
    args = parser.parse_args(argv)
    if handover and args.format != 'markdown':
        parser.error('Handover drafts use Markdown')
    try:
        summary = summarize(load(args.input))
        text = html(summary) if args.format == 'html' else markdown(summary, handover) if args.format == 'markdown' else json.dumps(summary, indent=2, ensure_ascii=True) + '\n'
        write_private(Path(args.output), text)
        print('Saved private ' + ('handover draft.' if handover else 'evidence report.') + ' Review before sharing; recovery is not inferred.')
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        print('Cannot export: use a supported schema-1 toolkit report and a new output file in an existing private directory.', file=sys.stderr)
        return 2


def console(document):
    """Readable bounded view; the saved JSON remains the full original report."""
    summary = summarize(document)
    lines = [summary['source_kind'] + ': ' + summary['decision']]
    if summary['example']:
        lines.append('ILLUSTRATIVE EXAMPLE — no real cluster observations')
    if summary['context']:
        lines.append('Context: ' + summary['context'] + ' | Namespace: ' + summary['namespace'])
    for row in summary['rows']:
        lines.append(row['status'] + ' ' + row['target'] + ': ' + row['evidence'])
        if row['next_step']:
            lines.append('  Next: ' + row['next_step'])
        if row['read_only_command']:
            lines.append('  Read: ' + row['read_only_command'])
    lines.extend('NOTE: ' + warning for warning in summary['warnings'])
    return '\n'.join(lines)
