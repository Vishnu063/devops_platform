"""Validate one approved patch with Kubernetes server dry-run, without persisting it."""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from .controls import ensure_enabled
from .policy import validate_file
from .recovery import fingerprint


def inspect(kube, policy):
    from .recovery import plan as image_plan
    from .repair import plan as repair_plan
    from .watch_recovery import failed_rollout
    images = 'approved_images' in policy
    kind = 'Deployment' if images else policy['kind']
    name = policy['deployment'] if images else policy['name']
    obj, namespace = kube.get(kind, name), kube.get('namespace', policy['namespace'])
    if images:
        patch, changes = image_plan(obj, namespace, policy, require_failure=False)
        desired = copy.deepcopy(obj['spec'])
        for container in desired['template']['spec']['containers']:
            container['image'] = policy['approved_images'][container['name']]
    else:
        hpas = kube.get('hpa')['items'] if policy['action'] == 'replicas' else []
        patch, desired = repair_plan(obj, namespace, policy, hpas, require_failure=False)
    expiry = datetime.fromisoformat(policy['expires_at'].replace('Z', '+00:00'))
    if expiry <= datetime.now(timezone.utc):
        raise ValueError('Policy expired before validation')
    ensure_enabled(kube.get('namespace', policy['namespace']), policy['namespace_uid'])
    result = json.loads(kube.run('patch', kind, name, '--type=json', '-p', json.dumps(patch),
                                 '--dry-run=server', '-o', 'json'))
    identity = policy['deployment_uid'] if images else policy['uid']
    if result['metadata']['uid'] != identity:
        raise ValueError('Dry-run identity mismatch')
    latch_key = 'devops-platform.io/recovery-attempt' if images else 'devops-platform.io/repair-attempt'
    latch_matches = result['metadata'].get('annotations', {}).get(latch_key) == patch[-1]['value']
    exact = result['spec'] == desired and latch_matches
    return {'schema_version': 1, 'kind': 'repair-dry-run',
            'created_at': datetime.now(timezone.utc).isoformat(), 'context': kube.context,
            'namespace': policy['namespace'], 'target': kind + '/' + name,
            'policy_sha256': fingerprint(policy), 'action': 'images' if images else policy['action'],
            'result': 'SERVER_ACCEPTED' if exact else 'NEEDS_REVIEW_ADMISSION_CHANGED_PATCH',
            'observed_failed_rollout': failed_rollout(obj) if kind == 'Deployment' else None,
            'failure_required_for_execution': images or policy.get('action') == 'containers',
            'persisted_patch': False,
            'limitations': ['The exact approved patch, including its attempt annotation, was submitted only with --dry-run=server.',
                            'The server evaluates authorization/admission but does not persist this request or its latch.',
                            'This does not start a rollout, test image pulls, prove capacity/readiness or authorize a later execution.',
                            'Live state and resourceVersion can change immediately; execute must recheck all original guards.']}


def main(argv=None):
    from .cli import Kube, QueryError, write_private
    parser = argparse.ArgumentParser(prog='devops-toolkit repair-dry-run')
    parser.add_argument('--policy', required=True)
    parser.add_argument('--output', help='New private JSON report')
    args = parser.parse_args(argv)
    try:
        policy = validate_file(args.policy)
        report = inspect(Kube(policy['context'], policy['namespace']), policy)
        if args.output:
            write_private(Path(args.output), json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0 if report['result'] == 'SERVER_ACCEPTED' else 1
    except (QueryError, OSError, ValueError, KeyError, TypeError, AttributeError):
        print('Server dry-run incomplete/refused: check policy, opt-in, pause, RBAC, admission and output path. No persistent patch was requested; no automatic retry.', file=sys.stderr)
        return 2
