"""Explain deployment risks using explicit live evidence and a JSON candidate."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys

from .policy import read_json, validate_file
from .recovery import fingerprint


def select_deployment(document, name, namespace):
    objects = document.get('items', []) if document.get('kind') == 'List' else [document]
    matches = [o for o in objects if o.get('kind') == 'Deployment' and o.get('metadata', {}).get('name') == name
               and o.get('metadata', {}).get('namespace', namespace) == namespace]
    if len(matches) != 1:
        raise ValueError('Exactly one target Deployment required')
    return matches[0], objects


def unavailable_count(value, replicas):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r'\d+%', value):
        percent = int(value[:-1])
        if percent <= 100:
            return math.floor(replicas * percent / 100)
    raise ValueError('Invalid maxUnavailable')


def availability(candidate, live):
    checks = []
    def add(status, name, detail):
        checks.append({'status': status, 'check': name, 'detail': detail})
    spec = candidate['spec']
    replicas = spec.get('replicas', 1)
    if type(replicas) is not int or replicas < 0:
        raise ValueError('Invalid replicas')
    if replicas == 0:
        add('WARN', 'availability:replicas', 'Desired replicas are zero; confirm intentional service unavailability')
    strategy = spec.get('strategy', {})
    if strategy.get('type', 'RollingUpdate') == 'Recreate':
        add('WARN', 'availability:strategy', 'Recreate removes old pods before replacement; interruption is possible')
    else:
        maximum = unavailable_count(strategy.get('rollingUpdate', {}).get('maxUnavailable', '25%'), replicas)
        add('WARN' if maximum else 'PASS', 'availability:strategy',
            f'Rollout permits {maximum} unavailable pod(s) from the desired count; this is configuration, not an uptime guarantee')
    if live is None:
        add('UNKNOWN', 'availability:baseline', 'No live baseline was available; downscaling and immutable-field changes are not checked')
    else:
        if spec.get('selector') != live['spec'].get('selector'):
            add('FAIL', 'availability:selector-immutable', 'Deployment selector differs from live state; in-place selector updates are immutable')
        old_replicas = live['spec'].get('replicas', 1)
        add('WARN' if replicas < old_replicas else 'PASS', 'availability:replica-change',
            f'Desired replicas {replicas}; current desired replicas {old_replicas}')
        if live.get('status', {}).get('availableReplicas', 0) < old_replicas:
            add('WARN', 'availability:baseline-health', 'Live deployment already has fewer available replicas than desired')
    if any(not c.get('readinessProbe') for c in spec['template']['spec'].get('containers', [])):
        add('FAIL', 'availability:readiness', 'A regular container has no readiness probe')
    return checks


def service_checks(service, deployment):
    name = service['metadata']['name']
    spec, pod_spec = service['spec'], deployment['spec']['template']['spec']
    selector = spec.get('selector')
    labels = deployment['spec']['template'].get('metadata', {}).get('labels', {})
    checks = []
    if spec.get('type') == 'ExternalName' or not selector:
        return [{'status': 'UNKNOWN', 'check': 'service:' + name, 'detail': 'Selectorless/ExternalName Service requires a separate routing review'}]
    matched = all(labels.get(k) == v for k, v in selector.items())
    checks.append({'status': 'PASS' if matched else 'FAIL', 'check': 'service:' + name,
                   'detail': 'Selector matches proposed pod labels' if matched else 'Service selector does not match proposed pod labels'})
    for port in spec.get('ports', []):
        target = port.get('targetPort', port['port'])
        protocol = port.get('protocol', 'TCP')
        if isinstance(target, str):
            matched_port = any(p.get('name') == target and p.get('protocol', 'TCP') == protocol
                               for c in pod_spec.get('containers', []) for p in c.get('ports', []))
            checks.append({'status': 'PASS' if matched_port else 'FAIL', 'check': 'service-port:' + name,
                           'detail': 'Named targetPort resolves in proposed containers' if matched_port else 'Named targetPort is not declared with the required protocol'})
        else:
            checks.append({'status': 'NOTE', 'check': 'service-port:' + name,
                           'detail': 'Numeric targetPort is configured; a listening application socket is not tested'})
    return checks


def recovery_check(path, candidate, namespace, live, context):
    if not path:
        return {'status': 'WARN', 'check': 'recovery', 'detail': 'No approval policy supplied; no automatic repair is authorized by this check'}
    policy = validate_file(path)
    images = 'approved_images' in policy
    name = policy.get('deployment') if images else policy.get('name')
    uid = policy.get('deployment_uid') if images else policy.get('uid')
    target_kind = 'Deployment' if images else policy.get('kind')
    bound = (policy['context'] == context and policy['namespace'] == candidate['metadata'].get('namespace', namespace['metadata']['name'])
             and policy['namespace_uid'] == namespace['metadata']['uid'] and target_kind == 'Deployment'
             and name == candidate['metadata']['name'] and live is not None and uid == live['metadata']['uid'])
    expected = fingerprint(candidate['spec']['template'] if images else candidate['spec'])
    bound = bound and policy.get('failed_template_sha256' if images else 'failed_spec_sha256') == expected
    annotations = candidate['metadata'].get('annotations', {})
    live_annotations = (live or {}).get('metadata', {}).get('annotations', {})
    key = 'allow-image-recovery' if images else 'allow-repair'
    opt_in = annotations.get('devops-platform.io/' + key, live_annotations.get('devops-platform.io/' + key)) == 'true'
    # Check-only: matching approval is not a guarantee that a future repair will be eligible.
    return {'status': 'PASS' if bound and opt_in else 'WARN', 'check': 'recovery',
            'detail': ('Unexpired policy matches this candidate and live identity; action: ' + ('images' if images else policy['action'])
                       + '. Repair must still pass live guards; no repair was started.') if bound and opt_in else
                      'Policy does not fully bind this candidate/live identity/opt-in; review or regenerate approval'}


def decision(checks):
    states = {c['status'] for c in checks}
    return 'BLOCKED' if 'FAIL' in states else 'NEEDS_REVIEW' if states & {'UNKNOWN', 'WARN'} else 'CHECKS_PASSED'


def run(kube, args):
    from .cli import preflight, QueryError
    namespace = kube.get('namespace', args.namespace)
    live = None
    try:
        live = kube.get('deployment', args.deployment)
    except QueryError:
        pass
    if args.file:
        candidate, objects = select_deployment(read_json(args.file, 8 * 1024 * 1024), args.deployment, args.namespace)
    elif live:
        candidate, objects = live, []
    else:
        raise ValueError('Supply a candidate JSON or an accessible live Deployment')
    checks = preflight(kube, args)['checks']
    # These state fixed scope limits rather than a discovered risk. Keep them visible,
    # but do not turn every check into NEEDS_REVIEW solely because a simulator is absent.
    for check in checks:
        if check['check'] in {'scheduler', 'admission'}:
            check['status'] = 'NOTE'
    checks.extend(availability(candidate, live))
    services = [o for o in objects if o.get('kind') == 'Service' and
                o.get('metadata', {}).get('namespace', args.namespace) == args.namespace and
                (not args.service or o['metadata']['name'] == args.service)]
    if not services and args.service:
        try:
            services = [kube.get('service', args.service)]
        except QueryError:
            pass
    if len(services) > 1 and not args.service:
        checks.append({'status': 'UNKNOWN', 'check': 'service:ambiguous', 'detail': 'Multiple candidate Services; specify --service to identify the intended target'})
        services = []
    if not services:
        checks.append({'status': 'UNKNOWN', 'check': 'service', 'detail': 'No Service supplied in candidate List; use --service to inspect an existing Service'})
    for service in services:
        checks.extend(service_checks(service, candidate))
    try:
        checks.append(recovery_check(args.policy, candidate, namespace, live, kube.context))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        checks.append({'status': 'FAIL', 'check': 'recovery', 'detail': 'Supplied approval policy is invalid, unreadable or expired'})
    # Recognized controller ownership overrides a superficially matching direct policy.
    for obj in [candidate] + ([live] if live else []):
        metadata = obj.get('metadata', {})
        keys = list(metadata.get('labels', {})) + list(metadata.get('annotations', {}))
        if any(k.startswith(('argocd.argoproj.io/', 'kustomize.toolkit.fluxcd.io/', 'helm.toolkit.fluxcd.io/')) for k in keys) or metadata.get('labels', {}).get('app.kubernetes.io/managed-by', '').lower() in {'argocd', 'flux'}:
            checks.append({'status': 'WARN', 'check': 'recovery:gitops', 'detail': 'Recognized GitOps ownership: correct and reconcile the approved Git source; direct recovery must not fight the controller'})
            break
    from .controls import ensure_enabled
    try:
        ensure_enabled(namespace)
    except ValueError:
        checks.append({'status': 'WARN', 'check': 'recovery:paused', 'detail': 'Direct repairs are currently disabled; a matching policy does not override the stop'})
    return {'schema_version': 1, 'kind': 'release-check', 'created_at': datetime.now(timezone.utc).isoformat(),
            'context': kube.context, 'namespace': args.namespace, 'deployment': args.deployment,
            'decision': decision(checks), 'checks': checks,
            'limitations': ['Image access uses local Docker credentials, not node pull identity; signature and architecture are not verified.',
                            'Capacity is a conservative one-pod CPU/memory estimate, not full rollout, quota or scheduler simulation.',
                            'Service checks compare labels and declared ports; they do not prove exclusive selection, endpoint readiness or traffic routing.',
                            'Secrets/ConfigMaps are checked in the live cluster, including keys; objects proposed in the same release are not assumed available.',
                            'Availability checks are configuration risks, not an outage prediction. CHECKS_PASSED is not deployment approval.']}


def main(argv=None):
    from .cli import Kube, QueryError, write_private
    parser = argparse.ArgumentParser(prog='devops-toolkit release-check')
    parser.add_argument('--context', required=True)
    parser.add_argument('--namespace', default='platform')
    parser.add_argument('--deployment', default='platform')
    parser.add_argument('--file', help='Deployment JSON or Kubernetes List JSON; render Helm YAML to JSON first')
    parser.add_argument('--service', help='Existing Service name, or a Service name in the supplied List')
    parser.add_argument('--policy', help='Optional existing approval policy, checked without executing it')
    parser.add_argument('--skip-image-check', action='store_true', help='Explicitly skip registry access; result requires review')
    parser.add_argument('--output', help='New private JSON report')
    args = parser.parse_args(argv)
    if not args.context.strip() or args.context.startswith('-') or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?', args.namespace) or any(name and not re.fullmatch(r'[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?', name) for name in (args.deployment, args.service)):
        parser.error('Use explicit context and valid resource names')
    args.verify_images = not args.skip_image_check
    try:
        report = run(Kube(args.context, args.namespace), args)
        if args.output:
            write_private(Path(args.output), json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 1 if report['decision'] == 'BLOCKED' else 2 if report['decision'] == 'NEEDS_REVIEW' else 0
    except (QueryError, OSError, ValueError, KeyError, TypeError, AttributeError):
        print('Release check incomplete: check candidate JSON, context, permissions and output path. No deployment or repair was performed.', file=sys.stderr)
        return 2
