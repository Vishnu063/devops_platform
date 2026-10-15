"""Offline configuration checks for CI. Never claims live deployment readiness."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from .manifests import source_arguments, source_document
from .release_check import service_checks, unavailable_count


def selector_matches(selector, labels):
    if not isinstance(selector, dict) or not selector:
        return False
    if any(labels.get(k) != v for k, v in selector.get('matchLabels', {}).items()):
        return False
    for expression in selector.get('matchExpressions', []):
        key, operator, values = expression['key'], expression['operator'], expression.get('values', [])
        if operator == 'In':
            matched = key in labels and labels[key] in values
        elif operator == 'NotIn':
            matched = key not in labels or labels[key] not in values
        elif operator == 'Exists':
            matched = key in labels
        elif operator == 'DoesNotExist':
            matched = key not in labels
        else:
            return False
        if not matched:
            return False
    return bool(selector.get('matchLabels') or selector.get('matchExpressions'))


def inspect(document, namespace):
    from .cli import quantity, references
    checks, deployments = [], []
    objects = document['items']
    def add(status, resource, name, detail):
        checks.append({'status': status, 'resource': resource, 'check': name, 'detail': detail})
    identities = set()
    for obj in objects:
        if obj['kind'] in {'Deployment', 'Service'}:
            key = (obj['kind'], obj['metadata'].get('namespace', namespace), obj['metadata']['name'])
            if key in identities:
                add('FAIL', obj['kind'] + '/' + obj['metadata']['name'], 'duplicate-target', 'Duplicate object in the effective namespace')
            identities.add(key)
    for obj in objects:
        if obj['kind'] != 'Deployment':
            continue
        if obj['apiVersion'] != 'apps/v1':
            add('FAIL', 'Deployment/' + obj['metadata']['name'], 'api-version', 'Supported Deployment API is apps/v1')
            continue
        metadata, spec = obj['metadata'], obj['spec']
        scope = metadata.get('namespace', namespace)
        resource = 'Deployment/' + metadata['name']
        pod = spec['template']['spec']
        labels = spec['template'].get('metadata', {}).get('labels', {})
        deployments.append((obj, scope))
        add('PASS' if selector_matches(spec.get('selector'), labels) else 'FAIL', resource,
            'deployment-selector', 'Deployment selector must match its own pod template labels')
        containers = pod.get('containers', [])
        if not containers:
            add('FAIL', resource, 'containers', 'No regular containers found')
        for container in containers + pod.get('initContainers', []):
            name = container['name']
            image = container.get('image', '')
            add('PASS' if re.fullmatch(r'[A-Za-z0-9._:/-]+@sha256:[a-f0-9]{64}', image) else 'FAIL', resource,
                'image:' + name, 'Use a digest-pinned image; registry existence is not checked offline')
            resources = container.get('resources', {})
            complete = all(k in resources.get(s, {}) for s in ('requests', 'limits') for k in ('cpu', 'memory'))
            valid = complete and all(quantity(resources['requests'][k]) <= quantity(resources['limits'][k]) for k in ('cpu', 'memory'))
            add('PASS' if valid else 'FAIL', resource, 'resources:' + name, 'CPU/memory requests and limits must be set and requests must fit limits')
            if container in containers:
                for probe in ('readinessProbe', 'livenessProbe'):
                    add('PASS' if container.get(probe) else 'FAIL', resource, probe + ':' + name, 'Health probe configuration is required; endpoint behavior is not tested')
        replicas = spec.get('replicas', 1)
        if type(replicas) is not int or replicas < 0:
            add('FAIL', resource, 'replicas', 'Replicas must be a nonnegative integer')
        else:
            if replicas == 0:
                add('WARN', resource, 'replicas', 'Scaled to zero; confirm intentional unavailability')
            strategy = spec.get('strategy', {})
            if strategy.get('type', 'RollingUpdate') == 'Recreate':
                add('WARN', resource, 'strategy', 'Recreate can interrupt availability')
            elif unavailable_count(strategy.get('rollingUpdate', {}).get('maxUnavailable', '25%'), replicas):
                add('WARN', resource, 'strategy', 'RollingUpdate permits unavailable pods; review the intended availability budget')
        if list(references(pod)):
            add('NOTE', resource, 'live-references', 'Required configuration references exist in the spec; object/key availability is not checked offline')
    if not deployments:
        add('FAIL', 'input', 'deployments', 'No Deployment found; this offline check targets Deployment workloads')
    for obj in objects:
        if obj['kind'] != 'Service':
            continue
        if obj['apiVersion'] != 'v1':
            add('FAIL', 'Service/' + obj['metadata']['name'], 'api-version', 'Supported Service API is core/v1')
            continue
        service_namespace = obj['metadata'].get('namespace', namespace)
        selector = obj.get('spec', {}).get('selector')
        same_namespace = [d for d, ns in deployments if ns == service_namespace]
        matched = [d for d in same_namespace if selector and all(
            d['spec']['template'].get('metadata', {}).get('labels', {}).get(k) == v for k, v in selector.items())]
        resource = 'Service/' + obj['metadata']['name']
        if not selector:
            add('NOTE', resource, 'selector', 'Selectorless Service requires separate routing review')
        elif not matched:
            # The Service can legitimately target workloads outside this input.
            add('WARN', resource, 'selector', 'Selector matches no Deployment in this namespace/input; external targets are not examined')
        else:
            if len(matched) > 1:
                add('WARN', resource, 'selector', 'Selector matches multiple rendered Deployments; confirm intended sharing')
            for deployment in matched:
                for check in service_checks(obj, deployment):
                    add(check['status'], resource, check['check'], check['detail'])
    states = {c['status'] for c in checks}
    return {'schema_version': 1, 'kind': 'offline-manifest-check',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'configuration_decision': 'BLOCKED' if 'FAIL' in states else 'CHECKS_PASSED_WITH_WARNINGS' if 'WARN' in states else 'CHECKS_PASSED',
            'deployment_readiness': 'NOT_ASSESSED_OFFLINE', 'checks': checks,
            'limitations': ['No cluster, registry, credentials, admission, node capacity or real traffic was checked.',
                            'Only implemented Deployment and Service rules are checked; this is not full Kubernetes schema validation.',
                            'Secret data, environment values, rendered manifests and arbitrary object fields are excluded from this report.']}


def main(argv=None):
    from .cli import write_private
    parser = argparse.ArgumentParser(prog='devops-toolkit manifest-check')
    source_arguments(parser, required=True)
    parser.add_argument('--namespace', default='platform')
    parser.add_argument('--output', help='New private JSON report')
    parser.add_argument('--warnings-as-errors', action='store_true')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?', args.namespace):
        parser.error('Use a valid namespace')
    try:
        report = inspect(source_document(args), args.namespace)
        if args.output:
            write_private(Path(args.output), json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 1 if report['configuration_decision'] == 'BLOCKED' or args.warnings_as_errors and report['configuration_decision'] == 'CHECKS_PASSED_WITH_WARNINGS' else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print('Offline check incomplete: inspect the input, install the YAML extra if needed and use a new output path. No cluster was contacted.', file=sys.stderr)
        return 2
