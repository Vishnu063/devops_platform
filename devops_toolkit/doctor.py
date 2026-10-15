"""Local prerequisite checks, with separately requested read-only access checks."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys


def inspect(profile, context=None, namespace='platform'):
    checks = []
    def add(status, name, detail):
        checks.append(dict(status=status, check=name, detail=detail))
    add('PASS' if sys.version_info >= (3, 12) else 'FAIL', 'python', 'Python 3.12 or later is required')
    tools = {'offline': [], 'cluster': ['kubectl'], 'release': ['kubectl', 'docker'],
             'helm': ['helm'], 'demo': ['kubectl', 'docker', 'kind']}[profile]
    for tool in tools:
        add('PASS' if shutil.which(tool) else 'FAIL', tool, tool + ' must be available on PATH')
    add('PASS' if importlib.util.find_spec('yaml') else 'NOTE', 'yaml',
        "YAML input needs the optional extra: python -m pip install '.[yaml]'; JSON works without it")
    if context:
        from .cli import Kube, QueryError
        kube = Kube(context, namespace)
        for resource in ['pods', 'deployments.apps', 'events', 'replicasets.apps', 'services',
                         'persistentvolumeclaims', 'horizontalpodautoscalers.autoscaling', 'jobs.batch']:
            try:
                allowed = kube.run('auth', 'can-i', 'list', resource).strip() == 'yes'
                add('PASS' if allowed else 'UNKNOWN', 'access:' + resource,
                    'List authorization reported allowed' if allowed else 'List authorization was not confirmed')
            except QueryError:
                add('UNKNOWN', 'access:' + resource, 'Cannot confirm access; check context, authentication and RBAC')
    return {'schema_version': 1, 'kind': 'doctor', 'profile': profile, 'checks': checks,
            'limitations': ['Local checks do not run tools, inspect credentials or contact a cluster unless --context is supplied.',
                            'Access checks are authorization observations, not a connectivity, health or readiness guarantee.',
                            'Registry login, Docker daemon, Helm version, admission and repair permissions are not verified.']}


def main(argv=None):
    from .cli import write_private
    import re
    parser = argparse.ArgumentParser(prog='devops-toolkit doctor')
    parser.add_argument('--profile', choices=['offline', 'cluster', 'release', 'helm', 'demo'], default='offline')
    parser.add_argument('--context', help='Opt in to read-only authorization queries against this context')
    parser.add_argument('--namespace', default='platform')
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    if (args.context is not None and (not args.context.strip() or args.context.startswith('-'))) or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?', args.namespace):
        parser.error('Use an explicit context and valid namespace')
    try:
        report = inspect(args.profile, args.context, args.namespace)
        if args.output:
            write_private(Path(args.output), json.dumps(report, indent=2) + '\n')
        for check in report['checks']:
            print(check['status'] + ' ' + check['check'] + ': ' + check['detail'])
        print('Prerequisites only; workload health and deployment readiness are not assessed.')
        states = {c['status'] for c in report['checks']}
        return 1 if 'FAIL' in states else 2 if 'UNKNOWN' in states else 0
    except (OSError, ValueError):
        print('Cannot save doctor report; use a new file in an existing private directory.', file=sys.stderr)
        return 2
