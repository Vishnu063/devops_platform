"""Fabricated offline learning fixtures. No commands or cluster reads."""
import argparse
import json
from pathlib import Path
import sys

SIGNALS = {'crash': 'CrashLoopBackOff', 'image': 'ImagePullBackOff', 'selector': 'ServiceSelectorMismatch'}


def fixture(scenario):
    from .diagnose import ADVICE
    signal = SIGNALS[scenario]
    action = ADVICE.get(signal, 'Compare the intended Service selector and pod labels, then inspect EndpointSlices and traffic. Do not guess labels.')
    return {'schema_version': 1, 'kind': 'diagnosis', 'example': True,
            'created_at': '2026-01-01T00:00:00+00:00', 'context': 'EXAMPLE-NOT-A-CLUSTER', 'namespace': 'example',
            'findings': [{'resource': 'pods/example-api' if scenario != 'selector' else 'services/example-api',
                          'signal': signal, 'next_action': action}], 'unavailable': [],
            'limitations': ['Fabricated training example. Nothing was queried, changed, repaired or verified.',
                            'A symptom can have multiple causes; validate evidence before selecting an action.']}


def main(argv=None):
    from .cli import write_private
    parser = argparse.ArgumentParser(prog='devops-toolkit example')
    parser.add_argument('--scenario', choices=SIGNALS, default='crash')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        write_private(Path(args.output), json.dumps(fixture(args.scenario), indent=2) + '\n')
        print('Saved ILLUSTRATIVE offline example. No cluster was contacted or repaired.')
        return 0
    except OSError:
        print('Use a new output file in an existing private directory.', file=sys.stderr)
        return 2
