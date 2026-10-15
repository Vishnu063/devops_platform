"""Read-only, value-redacted comparison of desired manifest fields against live state."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from .manifests import source_arguments, source_document

# Keep reports within fields useful for supported workload recovery. No object dumps.
RESOURCE_TYPES = {'Deployment': 'deployments.apps', 'Service': 'services'}


def differences(desired, live, path='', rows=None):
    rows = [] if rows is None else rows
    if len(rows) >= 500:
        return rows
    if isinstance(desired, dict):
        if not isinstance(live, dict):
            rows.append({'path': path or '/', 'change': 'type-or-presence-differs'})
        else:
            for key, value in desired.items():
                escaped = str(key).replace('~', '~0').replace('/', '~1')
                child = path + '/' + escaped
                if key not in live:
                    rows.append({'path': child, 'change': 'desired-field-not-observed'})
                else:
                    differences(value, live[key], child, rows)
                if len(rows) >= 500:
                    break
    elif isinstance(desired, list):
        if not isinstance(live, list) or len(desired) != len(live):
            rows.append({'path': path, 'change': 'list-shape-differs'})
        else:
            for index, item in enumerate(desired):
                differences(item, live[index], path + '/' + str(index), rows)
                if len(rows) >= 500:
                    break
    elif type(desired) != type(live) or desired != live:
        rows.append({'path': path, 'change': 'value-differs'})
    return rows


def projection(obj):
    metadata = obj.get('metadata', {})
    result = {'spec': obj.get('spec', {})}
    if 'labels' in metadata:
        result['metadata'] = {'labels': metadata['labels']}
    return result


def inspect(kube, document):
    from .cli import QueryError
    reports, unavailable, unsupported = [], [], []
    targets = set()
    for obj in document['items']:
        kind, name = obj['kind'], obj['metadata']['name']
        if kind not in RESOURCE_TYPES or obj.get('apiVersion') != ('apps/v1' if kind == 'Deployment' else 'v1'):
            unsupported.append(kind + '/' + name)
            continue
        if obj['metadata'].get('namespace', kube.namespace) != kube.namespace:
            raise ValueError('Cross-namespace input refused')
        target = kind + '/' + name
        if target in targets:
            raise ValueError('Duplicate target in effective namespace')
        targets.add(target)
        try:
            live = kube.get(RESOURCE_TYPES[kind], name)
            rows = differences(projection(obj), projection(live))
            reports.append({'resource': target, 'uid': live['metadata']['uid'], 'fields': rows,
                            'truncated': len(rows) >= 500})
        except QueryError:
            unavailable.append(target)  # NotFound, Forbidden and network errors remain uncertain.
    if not reports and not unavailable:
        raise ValueError('No supported Deployment/Service targets')
    return {'schema_version': 1, 'kind': 'drift-report', 'created_at': datetime.now(timezone.utc).isoformat(),
            'context': kube.context, 'namespace': kube.namespace, 'resources': reports,
            'unavailable': unavailable, 'unsupported': unsupported,
            'has_observed_drift': any(r['fields'] for r in reports),
            'limitations': ['Only desired spec fields and explicitly supplied labels are compared; unspecified live fields and annotations/status are ignored.',
                            'Lists are compared by position/shape; defaults, injection, quantity representations and reordering can produce noise.',
                            'Values are omitted, but paths/resource names can be sensitive. This is not a full GitOps semantic diff or deletion detector.',
                            'Unknown targets are not assumed missing. No configuration is changed or reconciled.']}


def main(argv=None):
    from .cli import Kube, QueryError, write_private
    parser = argparse.ArgumentParser(prog='devops-toolkit drift')
    parser.add_argument('--context', required=True)
    parser.add_argument('--namespace', default='platform')
    source_arguments(parser, required=True)
    parser.add_argument('--output', help='New private JSON report')
    args = parser.parse_args(argv)
    if not args.context.strip() or args.context.startswith('-') or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?', args.namespace):
        parser.error('Use explicit context and valid namespace')
    try:
        report = inspect(Kube(args.context, args.namespace), source_document(args))
        if args.output:
            write_private(Path(args.output), json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 2 if report['unavailable'] or report['unsupported'] or any(r['truncated'] for r in report['resources']) else 1 if report['has_observed_drift'] else 0
    except (QueryError, OSError, ValueError, KeyError, TypeError, AttributeError):
        print('Drift report incomplete: check input, context, permissions and new output path. No configuration was changed.', file=sys.stderr)
        return 2
