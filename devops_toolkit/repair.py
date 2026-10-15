"""Opt-in, exact-state repair of approved Deployment fields or Service selectors.

No arbitrary commands, secret data, object deletion, or repeated patch attempts.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time

from .recovery import PREFIX, fingerprint, audit_write, recovered
from .watch_recovery import failed_rollout
from .controls import ensure_enabled

FIELDS = {'image', 'resources', 'envFrom', 'env', 'readinessProbe',
          'livenessProbe', 'startupProbe', 'securityContext'}


def load_policy(path):
    with open(path, 'rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Policy too large')
    p = json.loads(raw)
    required = {'context', 'namespace', 'namespace_uid', 'kind', 'name', 'uid',
                'failed_spec_sha256', 'expires_at', 'action', 'approved'}
    if not isinstance(p, dict) or set(p) != required:
        raise ValueError('Invalid policy schema')
    for key in required - {'approved'}:
        if not isinstance(p[key], str) or not p[key] or p[key].startswith('-'):
            raise ValueError('Invalid identity')
    for key, limit in [('namespace', 63), ('name', 253)]:
        if len(p[key]) > limit or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?', p[key]):
            raise ValueError('Invalid name')
    if '.' in p['namespace']:
        raise ValueError('Invalid namespace')
    if not re.fullmatch('[a-f0-9]{64}', p['failed_spec_sha256']):
        raise ValueError('Invalid spec hash')
    check_expiry(p)
    if (p['kind'], p['action']) not in {('Deployment', 'containers'),
            ('Deployment', 'replicas'), ('Service', 'selector')}:
        raise ValueError('Unsupported repair')
    approved = p['approved']
    if p['action'] == 'replicas':
        if type(approved) is not int or not 1 <= approved <= 10:
            raise ValueError('Approved replicas must be 1..10')
    elif not isinstance(approved, dict) or not approved:
        raise ValueError('Approved fields must be nonempty')
    elif p['action'] == 'selector':
        if any(not isinstance(k, str) or not k or not isinstance(v, str) or not v
               for k, v in approved.items()):
            raise ValueError('Invalid selector')
    else:
        for name, fields in approved.items():
            if not isinstance(name, str) or not isinstance(fields, dict) or not fields or not set(fields) <= FIELDS:
                raise ValueError('Unsupported container field')
            if 'image' in fields and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9./:_-]*@sha256:[a-f0-9]{64}', str(fields['image'])):
                raise ValueError('Images must be immutable digests')
            # Reference existing secrets; never put plaintext env values in a repair policy.
            for env in fields.get('env', []):
                if set(env) != {'name', 'valueFrom'} or not env['valueFrom'] or not set(env['valueFrom']) <= {'secretKeyRef', 'configMapKeyRef', 'fieldRef', 'resourceFieldRef'}:
                    raise ValueError('Only environment references are supported')
    return p


def check_expiry(p):
    expiry = datetime.fromisoformat(p['expires_at'].replace('Z', '+00:00'))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError('Expired policy')


def plan(obj, namespace, p, hpas, *, require_failure=True):
    check_expiry(p)
    ensure_enabled(namespace, p["namespace_uid"])
    m, spec = obj['metadata'], obj['spec']
    if (obj['kind'], m['name'], m['namespace'], m['uid']) != (p['kind'], p['name'], p['namespace'], p['uid']):
        raise ValueError('Target changed')
    if namespace['metadata']['uid'] != p['namespace_uid']:
        raise ValueError('Namespace changed')
    a, labels = m.get('annotations', {}), m.get('labels', {})
    if a.get(PREFIX + 'allow-repair') != 'true' or a.get(PREFIX + 'repair-attempt'):
        raise ValueError('No opt-in or already attempted')
    if m.get('deletionTimestamp') or spec.get('paused'):
        raise ValueError('Deleting or paused')
    if any(k.startswith(('argocd.argoproj.io/', 'kustomize.toolkit.fluxcd.io/', 'helm.toolkit.fluxcd.io/'))
           for k in list(a) + list(labels)) or labels.get('app.kubernetes.io/managed-by', '').lower() in {'argocd', 'flux'}:
        raise ValueError('Repair GitOps source instead')
    if fingerprint(spec) != p['failed_spec_sha256']:
        raise ValueError('Spec changed')
    patch = [{'op': 'test', 'path': '/metadata/uid', 'value': m['uid']},
             {'op': 'test', 'path': '/metadata/resourceVersion', 'value': m['resourceVersion']}]
    desired = copy.deepcopy(spec)
    if p['action'] == 'containers':
        if spec.get('replicas', 1) < 1 or (require_failure and not failed_rollout(obj)):
            raise ValueError('Only observed failed rollouts are eligible')
        containers = desired['template']['spec']['containers']
        if not set(p['approved']) <= {c['name'] for c in containers}:
            raise ValueError('Unknown container')
        for container in containers:
            container.update(p['approved'].get(container['name'], {}))
        patch.append({'op': 'replace', 'path': '/spec/template/spec/containers', 'value': containers})
    elif p['action'] == 'replicas':
        if any(h.get('spec', {}).get('scaleTargetRef', {}).get('kind') == 'Deployment' and
               h['spec']['scaleTargetRef'].get('name') == p['name'] for h in hpas):
            raise ValueError('Autoscaler owns replica count')
        if not 0 < spec.get('replicas', 1) < p['approved']:
            raise ValueError('Only restore a nonzero count upward; maximum 10')
        desired['replicas'] = p['approved']
        patch.append({'op': 'add', 'path': '/spec/replicas', 'value': p['approved']})
    else:
        if spec.get('type', 'ClusterIP') != 'ClusterIP' or spec.get('publishNotReadyAddresses'):
            raise ValueError('Only ordinary ClusterIP Services are eligible')
        desired['selector'] = p['approved']
        patch.append({'op': 'add', 'path': '/spec/selector', 'value': p['approved']})
    if desired == spec:
        raise ValueError('No repair needed')
    patch.append({'op': 'add', 'path': '/metadata/annotations/devops-platform.io~1repair-attempt',
                  'value': fingerprint(p)})
    return patch, desired


def service_ready(kube, obj):
    slices = kube.get('endpointslices', '-l', 'kubernetes.io/service-name=' + obj['metadata']['name'])['items']
    return any(any(owner.get('uid') == obj['metadata']['uid'] and owner.get('kind') == 'Service'
                   for owner in item.get('metadata', {}).get('ownerReferences', [])) and
               any(e.get('conditions', {}).get('ready') is True and
                   not e.get('conditions', {}).get('terminating', False) and e.get('addresses')
                   for e in item.get('endpoints', [])) for item in slices)


def monitor(path, execute=False, audit=None, interval=15, max_wait=900, timeout=180):
    from .cli import Kube
    p = load_policy(path)
    policy_hash = fingerprint(p)
    kube = Kube(p['context'], p['namespace'])
    if execute and (not audit or Path(audit).exists() or not Path(audit).parent.is_dir()):
        raise ValueError('Use a new private audit path')
    deadline, observations = time.monotonic() + max_wait, 0
    while time.monotonic() < deadline:
        if fingerprint(load_policy(path)) != policy_hash:
            raise ValueError('Policy changed')
        obj = kube.get(p['kind'], p['name'])
        namespace = kube.get('namespace', p['namespace'])
        # Fail closed when HPA access is unavailable. Other scaling controllers must
        # be excluded by the operator before opt-in; Kubernetes has no universal list.
        hpas = kube.get('hpa')['items'] if p['action'] == 'replicas' else []
        # Container recovery waits for the failed-rollout signal, still requiring exact scope.
        if p['action'] == 'containers' and not failed_rollout(obj):
            plan(obj, namespace, p, hpas, require_failure=False)
            if recovered(obj, obj):
                print('Deployment ready; no repair needed.', flush=True)
                return 0
            observations = 0
        else:
            patch, desired = plan(obj, namespace, p, hpas)
            observations += 1
            if observations >= 3:
                print(json.dumps({'mode': 'execute' if execute else 'preview', 'action': p['action'],
                                  'target': p['name'], 'approved_policy_sha256': policy_hash}), flush=True)
                if not execute:
                    return 0
                # Persist intent before the single conditional mutation. A lost API
                # response never triggers a retry. Do not log potentially secret field values.
                fd = os.open(audit, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    audit_write(stream, 'intent', policy_sha256=policy_hash, uid=p['uid'], action=p['action'], context=p['context'], namespace=p['namespace'], kind=p['kind'], target=p['name'])
                    try:
                        if fingerprint(load_policy(path)) != policy_hash:
                            raise ValueError('Policy changed before patch')
                        ensure_enabled(kube.get('namespace', p['namespace']), p['namespace_uid'])
                        applied = json.loads(kube.run('patch', p['kind'], p['name'], '--type=json', '-p', json.dumps(patch), '-o', 'json'))
                        audit_write(stream, 'patch_acknowledged')
                        if applied['spec'] != desired or applied['metadata']['uid'] != p['uid']:
                            raise ValueError('Admission changed approved spec')
                        end, stable = time.monotonic() + timeout, 0
                        while time.monotonic() < end:
                            current = kube.get(p['kind'], p['name'])
                            if current['metadata']['uid'] != p['uid'] or current['spec'] != applied['spec']:
                                raise ValueError('Concurrent spec change')
                            ready = recovered(current, applied) if p['kind'] == 'Deployment' else service_ready(kube, current)
                            stable = stable + 1 if ready else 0
                            if stable >= 3:
                                audit_write(stream, 'readiness_confirmed')
                                print('Readiness confirmed. Verify application health separately.', flush=True)
                                return 0
                            time.sleep(5)
                        audit_write(stream, 'verification_timeout')
                        return 1
                    except Exception:
                        audit_write(stream, 'outcome_unknown', note='Inspect state; do not retry blindly')
                        raise
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
    print('Monitoring timeout; no mutation attempted.', flush=True)
    return 1


def main(argv=None):
    from .cli import QueryError
    parser = argparse.ArgumentParser(prog='python -m devops_toolkit repair')
    parser.add_argument('--policy', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--audit')
    parser.add_argument('--interval', type=int, choices=range(5, 61), default=15)
    parser.add_argument('--max-wait', type=int, choices=range(30, 3601), default=900)
    parser.add_argument('--timeout', type=int, choices=range(30, 601), default=180)
    args = parser.parse_args(argv)
    try:
        return monitor(args.policy, args.execute, args.audit, args.interval, args.max_wait, args.timeout)
    except (QueryError, OSError, ValueError, KeyError, TypeError, AttributeError, KeyboardInterrupt):
        print('Repair stopped. Inspect policy, private audit and live state. No automatic retry.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
