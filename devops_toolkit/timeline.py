"""Build a scoped incident timeline offline from selected snapshots and audits."""
import argparse
from datetime import datetime
import json
import re
from pathlib import Path
import sys

from .compare import load_snapshot, compare_files

AUDIT_LABELS = {'intent': 'Approved repair intent recorded',
                'patch_acknowledged': 'API acknowledged the repair patch',
                'deployment_ready': 'Deployment readiness confirmed',
                'readiness_confirmed': 'Resource readiness confirmed',
                'verification_timeout': 'Readiness not confirmed before timeout',
                'outcome_unknown': 'Outcome unknown; inspect live state before retry'}
AUDIT_EVENTS = {'intent', 'patch_acknowledged', 'deployment_ready', 'readiness_confirmed',
                'verification_timeout', 'outcome_unknown'}


def moment(text):
    result = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result


def build(snapshot_paths, audit_paths=()):
    if not 1 <= len(snapshot_paths) <= 50 or len(audit_paths) > 50:
        raise ValueError('Use 1..50 snapshots and at most 50 audits')
    snapshots = sorted([(str(p), load_snapshot(p)[0]) for p in snapshot_paths], key=lambda item: moment(item[1]['created_at']))
    first = snapshots[0][1]
    context, namespace = first['context'], first['namespace']
    entries, warnings = [], []
    for index, (path, snapshot) in enumerate(snapshots):
        if (snapshot['context'], snapshot['namespace']) != (context, namespace):
            raise ValueError('Snapshots must share context and namespace')
        unhealthy = sum(p.get('phase') != 'Running' or not p.get('containers') or any(not c.get('ready') for c in p.get('containers', []))
                        for p in snapshot['pods'])
        entries.append({'time': snapshot['created_at'], 'source': 'snapshot',
                        'summary': f"Captured {len(snapshot['pods'])} pods; {unhealthy} with non-running/not-ready evidence"})
        for pod in snapshot['pods']:
            for c in pod.get('containers', []):
                if c.get('reason'):
                    entries.append({'time': snapshot['created_at'], 'source': 'symptom',
                                    'summary': 'pod/' + pod['name'] + ' container/' + c['name'] + ': ' + str(c['reason'])})
        for event in snapshot['events']:
            if event.get('type') == 'Warning':
                entries.append({'time': snapshot['created_at'], 'source': 'warning captured',
                                'summary': str(event.get('object') or 'unknown') + ': ' + str(event.get('reason') or 'UnknownWarning')})
        if snapshot.get('unavailable') or snapshot.get('pods_truncated'):
            warnings.append('A snapshot is partial; absence is not proof of deletion or health')
        if index:
            comparison = compare_files(snapshots[index - 1][0], path)
            warnings.extend(comparison['warnings'])
            for finding in comparison['findings']:
                entries.append({'time': snapshot['created_at'], 'source': 'change observed',
                                'summary': finding['resource'] + ': ' + finding['message'],
                                'before': finding['before'], 'after': finding['after']})
    for path in audit_paths:
        with Path(path).open('rb') as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('Audit too large')
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
        if not records or records[0].get('event') != 'intent':
            raise ValueError('Audit must begin with intent')
        intent = records[0]
        if 'context' not in intent or 'namespace' not in intent:
            warnings.append('Skipped a legacy audit without scope; regenerate scoped audit evidence for correlation')
            continue
        if (intent['context'], intent['namespace']) != (context, namespace):
            raise ValueError('Audit scope differs from snapshots')
        previous = moment(intent['time'])
        for record in records:
            current = moment(record['time'])
            if current < previous:
                raise ValueError('Audit time moves backwards')
            previous = current
            if record.get('event') in AUDIT_EVENTS:
                entries.append({'time': record['time'], 'source': 'repair audit',
                                'summary': AUDIT_LABELS[record['event']], 'event': record['event'], 'action': intent.get('action', 'images')})
        if records[-1].get('event') not in {'deployment_ready', 'readiness_confirmed', 'verification_timeout', 'outcome_unknown'}:
            warnings.append('An audit has no terminal outcome; repair completion is unknown')
    entries.sort(key=lambda item: moment(item['time']))
    warnings.extend(['Snapshot change times are observation times, not the exact moment a change occurred.',
                     'Context names do not prove physical cluster identity; review scope and workload UIDs.',
                     'This timeline correlates evidence; it does not prove root cause or business recovery.'])
    return {'schema_version': 1, 'kind': 'incident-timeline', 'context': context,
            'namespace': namespace, 'entries': entries, 'warnings': list(dict.fromkeys(warnings))}


def markdown(report):
    def escape(value):
        text = re.sub(r'[\x00-\x1f\x7f]', ' ', str(value))
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return re.sub(r'([\\`*_{ }\[\]()|])'.replace(' ', ''), r'\\\1', text)
    lines = ['# Incident timeline', '', '| Observed time | Source | Evidence |', '| --- | --- | --- |']
    for entry in report['entries']:
        text = entry['summary']
        if 'action' in entry:
            text += ' — approved action: ' + str(entry['action'])
        if 'before' in entry:
            text += ' ' + json.dumps(entry['before'], ensure_ascii=True) + ' → ' + json.dumps(entry['after'], ensure_ascii=True)
        lines.append('| ' + ' | '.join(escape(v) for v in (entry['time'], entry['source'], text)) + ' |')
    lines += ['', *['- ' + escape(w) for w in report['warnings']], '']
    return '\n'.join(lines)


def main(argv=None):
    from .cli import write_private
    parser = argparse.ArgumentParser(prog='devops-toolkit timeline')
    parser.add_argument('snapshots', nargs='+')
    parser.add_argument('--audit', action='append', default=[])
    parser.add_argument('--format', choices=['json', 'markdown'], default='markdown')
    parser.add_argument('--output', help='New private file; parent must exist')
    args = parser.parse_args(argv)
    try:
        report = build(args.snapshots, args.audit)
        text = markdown(report) if args.format == 'markdown' else json.dumps(report, indent=2, ensure_ascii=True) + '\n'
        if args.output:
            write_private(Path(args.output), text)
            print('Saved private timeline.')
        else:
            # JSON keeps control characters escaped in terminal output.
            print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print('Cannot build timeline: use valid same-scope snapshots, scoped ordered audits and a new output file.', file=sys.stderr)
        return 2
