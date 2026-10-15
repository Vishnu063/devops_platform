"""Create a private approval policy from live identity and an explicit known fix."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import tempfile

from .recovery import fingerprint


def read_json(path, limit=65536):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Input too large')
    return json.loads(raw)


def validate_file(path):
    from .recovery import load_policy as image_policy
    from .repair import load_policy as repair_policy
    data = read_json(path)
    return image_policy(path) if 'approved_images' in data else repair_policy(path)


def build_policy(kube, name, kind, action, approved, minutes=20):
    from .recovery import load_policy as image_policy, plan as image_plan
    from .repair import load_policy as repair_policy, plan as repair_plan
    obj, namespace = kube.get(kind, name), kube.get('namespace', kube.namespace)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    if action == 'images':
        if kind != 'Deployment':
            raise ValueError('Image recovery requires Deployment')
        policy = {'context': kube.context, 'namespace': kube.namespace,
                  'namespace_uid': namespace['metadata']['uid'], 'deployment': name,
                  'deployment_uid': obj['metadata']['uid'],
                  'failed_template_sha256': fingerprint(obj['spec']['template']),
                  'approved_images': approved, 'expires_at': expires}
    else:
        policy = {'context': kube.context, 'namespace': kube.namespace,
                  'namespace_uid': namespace['metadata']['uid'], 'kind': kind, 'name': name,
                  'uid': obj['metadata']['uid'], 'failed_spec_sha256': fingerprint(obj['spec']),
                  'action': action, 'approved': approved, 'expires_at': expires}
    # Use the actual policy loaders; do not maintain a second interpretation of approval.
    with tempfile.TemporaryDirectory(prefix='devops-policy-') as directory:
        path = Path(directory) / 'policy.json'
        from .cli import write_private
        write_private(path, json.dumps(policy))
        validated = (image_policy if action == 'images' else repair_policy)(path)
    if action == 'images':
        image_plan(obj, namespace, validated, require_failure=False)
    else:
        hpas = kube.get('hpa')['items'] if action == 'replicas' else []
        repair_plan(obj, namespace, validated, hpas, require_failure=False)
    return policy


def main(argv=None):
    from .cli import Kube, QueryError, write_private
    parser = argparse.ArgumentParser(prog='devops-toolkit policy')
    commands = parser.add_subparsers(dest='operation', required=True)
    create = commands.add_parser('create', help='Read live UIDs/spec and combine with your approved correction')
    create.add_argument('--context', required=True)
    create.add_argument('--namespace', default='platform')
    create.add_argument('--kind', choices=['Deployment', 'Service'], default='Deployment')
    create.add_argument('--name', required=True)
    create.add_argument('--action', choices=['images', 'containers', 'replicas', 'selector'], required=True)
    create.add_argument('--approved', required=True, help='JSON containing only the explicit approved fix')
    create.add_argument('--expires-in', type=int, choices=range(5, 61), default=20, metavar='5..60')
    create.add_argument('--output', required=True, help='New private policy file; parent must exist')
    check = commands.add_parser('check', help='Check policy schema and expiry offline; no cluster contact')
    check.add_argument('path')
    args = parser.parse_args(argv)
    try:
        if args.operation == 'check':
            policy = validate_file(args.path)
            print(json.dumps({'valid': True, 'expires_at': policy['expires_at'],
                              'policy_sha256': fingerprint(policy), 'live_state_checked': False}))
            return 0
        if not args.context.strip() or args.context.startswith('-') or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?', args.namespace) or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?', args.name):
            parser.error('Use explicit context and valid names')
        policy = build_policy(Kube(args.context, args.namespace), args.name, args.kind,
                              args.action, read_json(args.approved), args.expires_in)
        write_private(Path(args.output), json.dumps(policy, indent=2) + '\n')
        print(json.dumps({'saved': args.output, 'action': args.action, 'expires_at': policy['expires_at'],
                          'policy_sha256': fingerprint(policy), 'cluster_mutated': False}))
        return 0
    except (QueryError, OSError, ValueError, KeyError, TypeError, AttributeError):
        print('Policy not created/validated: check approved JSON, opt-in, ownership, scope, expiry, live access and a new output path. No cluster changes were made.', file=sys.stderr)
        return 2
