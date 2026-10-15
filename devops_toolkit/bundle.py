"""Collect a private, ownership-scoped Deployment troubleshooting bundle."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys


def controlled_by(obj, kind, uids):
    return any(ref.get('kind') == kind and ref.get('uid') in uids and ref.get('controller') is True
               for ref in obj.get('metadata', {}).get('ownerReferences', []))


def collect(kube, args):
    from .cli import QueryError, incident, write_private
    deployment = kube.get('deployment', args.deployment)
    uid = deployment['metadata']['uid']
    unavailable = []
    def dataset(kind):
        try:
            return kube.get(kind)['items']
        except QueryError:
            unavailable.append(kind)
            return []
    replicasets = [r for r in dataset('replicasets') if controlled_by(r, 'Deployment', {uid})]
    rs_uids = {r['metadata']['uid'] for r in replicasets}
    pods = [p for p in dataset('pods') if controlled_by(p, 'ReplicaSet', rs_uids)]
    labels = deployment['spec']['template'].get('metadata', {}).get('labels', {})
    services = [s for s in dataset('services') if s.get('spec', {}).get('selector') and
                all(labels.get(k) == v for k, v in s['spec']['selector'].items())]
    resource_uids = {uid} | rs_uids | {p['metadata']['uid'] for p in pods} | {s['metadata']['uid'] for s in services}
    events = [e for e in dataset('events') if e.get('involvedObject', {}).get('uid') in resource_uids]
    try:
        namespace_uid = kube.get('namespace', kube.namespace)['metadata']['uid']
    except QueryError:
        namespace_uid = None
        unavailable.append('namespace')
    data = {'pods': pods, 'deployments': [deployment], 'events': events}
    allowed_pods = {p['metadata']['name'] for p in pods}
    class ScopedKube:
        def get(self, kind, *arguments):
            if kind not in data or kind in unavailable:
                raise QueryError('Scoped collection unavailable')
            return {'items': data[kind]}
        def run(self, *arguments):
            if len(arguments) < 2 or arguments[0] != 'logs' or arguments[1] not in allowed_pods:
                raise QueryError('Only selected workload logs are allowed')
            return kube.run(*arguments)
    directory, evidence = incident(ScopedKube(), args)
    report = {'schema_version': 1, 'kind': 'workload-bundle',
              'created_at': datetime.now(timezone.utc).isoformat(), 'context': kube.context,
              'namespace': kube.namespace, 'namespace_uid': namespace_uid,
              'deployment_scope': {'name': args.deployment, 'uid': uid}, **evidence}
    report['unavailable'] = sorted(set(report['unavailable'] + unavailable))
    report['limitations'].extend([
        'Pods are selected by Deployment → controller ReplicaSet → controller Pod ownership, not labels alone.',
        'Missing ReplicaSet access prevents pod ownership selection; zero selected pods is not a health claim.',
        'Service selection is label compatibility with the pod template, not exclusive ownership or proven traffic.',
        'No Secrets/ConfigMaps, environment values, annotations, event messages or arbitrary spec dumps are retained.',
        'Logs are opt-in, current regular containers only, bounded and redacted best effort; review before sharing.'])
    write_private(directory/'report.json', json.dumps(report, indent=2) + '\n')
    workload = {'deployment': {'name': args.deployment, 'uid': uid},
                'replicasets': [{'name': r['metadata']['name'], 'uid': r['metadata']['uid']} for r in replicasets[:100]],
                'services': [{'name': s['metadata']['name'], 'uid': s['metadata']['uid'],
                              'ports': [{'port': p.get('port'), 'targetPort': p.get('targetPort'),
                                         'protocol': p.get('protocol', 'TCP')} for p in s.get('spec', {}).get('ports', [])]}
                             for s in services[:100]],
                'replicaset_count': len(replicasets), 'service_count': len(services)}
    write_private(directory/'workload.json', json.dumps(workload, indent=2) + '\n')
    summary = '# Workload troubleshooting bundle\n\n' + (
        'Collection is partial; inspect unavailable in report.json.\n' if report['unavailable'] else
        'Selected evidence collected; this is not a health guarantee.\n')
    summary += '\nReview report.json and workload.json locally. Logs, if requested, require manual review before sharing.\nNo report was uploaded and no cluster change was made.\n'
    write_private(directory/'README.md', summary)
    return directory, report


def main(argv=None):
    from .cli import Kube, QueryError
    parser = argparse.ArgumentParser(prog='devops-toolkit bundle')
    parser.add_argument('--context', required=True)
    parser.add_argument('--namespace', default='platform')
    parser.add_argument('--deployment', required=True)
    parser.add_argument('--output', required=True, help='New private directory')
    parser.add_argument('--include-logs', action='store_true')
    parser.add_argument('--max-pods', type=int, choices=range(1, 51), default=10, metavar='1..50')
    args = parser.parse_args(argv)
    if not args.context.strip() or args.context.startswith('-') or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?', args.namespace) or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?', args.deployment):
        parser.error('Use explicit context and valid target names')
    try:
        directory, report = collect(Kube(args.context, args.namespace), args)
        print('Saved private workload evidence to ' + json.dumps(str(directory)))
        if report['unavailable']:
            print('Collection is partial; inspect unavailable in report.json.')
        return 2 if report['unavailable'] else 0
    except (QueryError, OSError, ValueError, KeyError, TypeError, AttributeError):
        print('Bundle incomplete: check context, ownership-read permissions and a new output directory. No cluster changes or uploads were made.', file=sys.stderr)
        return 2
