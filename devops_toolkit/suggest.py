"""Offline troubleshooting suggestions. Never executes commands or repairs."""
import argparse
import json
from pathlib import Path
import shlex
import sys

# These are investigation paths, not automatically inferred root causes.
PLAYBOOKS = {
    'crash': {
        'signals': ['crashloopbackoff', 'runcontainererror'],
        'causes': ['Application exits, invalid startup configuration, dependency failure or probe termination.'],
        'steps': ['Inspect current/previous container state and exit code; review previous logs locally.',
                  'Check entrypoint, configuration references, dependencies and startup/probe timing.',
                  'Correct the verified application/configuration issue through the owning delivery process.'],
        'verify': 'Confirm restarts stop increasing, readiness is stable and application requests succeed.'},
    'image': {
        'signals': ['imagepullbackoff', 'errimagepull', 'registry', 'image:'],
        'causes': ['Wrong digest/repository, unavailable registry, authentication, rate limiting or unsupported platform.'],
        'steps': ['Verify the exact image digest exists using the intended registry identity.',
                  'Check node-to-registry connectivity and imagePullSecret reference without exposing credentials.',
                  'Use only a reviewed compatible digest; a successful local pull does not prove node access.'],
        'verify': 'Confirm the intended digest is running and the application becomes ready.'},
    'memory': {
        'signals': ['oomkilled', 'memorypressure'],
        'causes': ['Container memory limit exceeded, a leak, a workload spike or node pressure.'],
        'steps': ['Compare termination reason, measured memory, configured limits and node pressure.',
                  'Investigate application growth/leaks and peak demand before adjusting budgets.',
                  'Review measured resource changes and node headroom; avoid unbounded limits or blind restarts.'],
        'verify': 'Observe representative load without repeated OOM events and with adequate node headroom.'},
    'configuration': {
        'signals': ['createcontainerconfigerror', 'reference:', 'live-references'],
        'causes': ['Required ConfigMap/Secret object or key is unavailable, or a configuration reference is incorrect.'],
        'steps': ['Compare the workload reference name, namespace and required key with the approved configuration.',
                  'Check access and object/key availability without copying values into evidence.',
                  'Restore the reviewed source or secret-delivery configuration; do not invent credentials.'],
        'verify': 'Confirm configuration errors disappear and the application starts and serves traffic.'},
    'scheduling': {
        'signals': ['failedscheduling', 'pending', 'capacity', 'resources:', 'limits:', 'diskpressure', 'pidpressure', 'networkunavailable'],
        'causes': ['Insufficient capacity, taints, affinity/topology, quota, storage binding or node health constraints.'],
        'steps': ['Read scheduling events locally and compare requests with eligible node headroom and quotas.',
                  'Review taints/tolerations, affinity/topology and PVC binding requirements.',
                  'Ask the owning platform team for reviewed capacity/configuration changes; do not remove constraints blindly.'],
        'verify': 'Confirm placement on an intended node and stable readiness; one-pod estimates do not prove rollout capacity.'},
    'probe': {
        'signals': ['unhealthy', 'notready', 'readinessprobe', 'livenessprobe', 'progressdeadlineexceeded'],
        'causes': ['Wrong probe path/port/timing, slow startup, application failure or unavailable dependencies.'],
        'steps': ['Compare probe configuration with the actual application listener and expected startup behavior.',
                  'Inspect application health and dependencies separately from pod phase.',
                  'Correct the confirmed issue through the reviewed source; retain meaningful health checks.'],
        'verify': 'Confirm sustained ready/available replicas and a successful application-level request.'},
    'service': {
        'signals': ['serviceselectormismatch', 'selector', 'service:', 'service-port:', 'endpoint'],
        'causes': ['Selector/label mismatch, unresolved targetPort, no ready endpoints or a separate network/routing failure.'],
        'steps': ['Compare the intended Service selector with the intended pod labels in the same namespace.',
                  'Check EndpointSlices and named-port/protocol resolution; selection alone does not prove traffic.',
                  'Review any selector correction for unintended targets, then use the owning GitOps/delivery flow.'],
        'verify': 'Confirm intended ready endpoints and real requests through the intended Service path.'},
    'storage': {
        'signals': ['failedmount', 'failedattachvolume', 'pvc:'],
        'causes': ['Missing volume reference, binding delay, CSI failure, attachment conflict or storage permissions.'],
        'steps': ['Inspect PVC phase, StorageClass/binding mode and volume events locally.',
                  'Check CSI health and attachment/node state with the storage owner.',
                  'Review the source/driver correction; do not delete PVCs or force-detach active storage.'],
        'verify': 'Confirm the intended volume mounts and application data checks pass without further storage errors.'},
    'autoscaling': {
        'signals': ['failedgetresourcemetric', 'failedcomputemetricsreplicas', 'scalingactive', 'scalinglimited', 'abletoscale', 'hpa'],
        'causes': ['Metrics unavailable, missing requests, intentional min/max bounds or unavailable capacity.'],
        'steps': ['Check HPA conditions, metrics availability and configured resource requests.',
                  'Compare actual demand with min/max bounds and eligible capacity.',
                  'Review controller configuration; do not fight HPA with repeated manual replica edits.'],
        'verify': 'Confirm metrics and expected scaling decisions over a representative observation period.'},
    'permissions': {
        'signals': ['forbidden', 'unauthorized', 'rbac', 'permission', 'failedcreate'],
        'causes': ['Expired/wrong identity, missing scoped authorization, quota or admission rejection.'],
        'steps': ['Verify the intended context, namespace and identity without printing credentials.',
                  'Use doctor with an explicit context for limited authorization observations; inspect admission/quota evidence separately.',
                  'Request the minimum required permission or reviewed policy correction through the owner.'],
        'verify': 'Repeat the intended read/check with the scoped identity; do not grant cluster-admin as a shortcut.'},
    'recovery': {
        'signals': ['recovery', 'gitops', 'paused', 'policy', 'latch', 'attempt', 'outcome_unknown', 'verification_timeout'],
        'causes': ['Expired/mismatched approval, stop control, GitOps/HPA ownership, previous attempt or uncertain patch outcome.'],
        'steps': ['Inspect the saved audit and live target identity/state before considering another action.',
                  'Review expiry, UID/hash binding, stop controls and controller ownership; a refusal is not permission to bypass a guard.',
                  'For GitOps, propose a reviewed source change. For unknown outcomes, involve the owner; never clear the latch and retry blindly.'],
        'verify': 'Require scoped terminal audit evidence, stable intended state and separate application-health checks.'},
    'toolkit-error': {
        'signals': ['toolkit-error', 'timeout', 'stuck', 'output', 'input', 'helm', 'docker'],
        'causes': ['Missing prerequisite, bad input, inaccessible context, network delay, unsupported field or an existing output path.'],
        'steps': ['Run doctor for the intended task and read COMMAND --help; confirm context and input format.',
                  'Check network/authentication locally and use a new output file under an existing private directory.',
                  'If a repair may have started, inspect its audit/live state before retrying. Stop if the outcome is unknown.'],
        'verify': 'Repeat only an appropriate read-only check after correcting the verified issue; do not replay mutations automatically.'},
    'unknown': {
        'signals': [],
        'causes': ['Available evidence does not identify a supported symptom or a proven root cause.'],
        'steps': ['Capture the exact symptom, affected scope, observation time and recent reviewed changes.',
                  'Collect a private diagnosis/bundle and compare same-scope evidence without exposing secrets.',
                  'Escalate to the workload/platform owner with evidence, impact and checks already attempted.'],
        'verify': 'Define the expected workload state and application-health check with the owner before changing anything.'},
}


def topic_for(signal):
    text = str(signal).lower()
    if text in PLAYBOOKS:
        return text
    if 'pvc:' in text:
        return 'storage'
    if 'deployment-selector' in text or 'selector-immutable' in text:
        # A Deployment selector is not a Service selector; use owner review.
        return 'unknown'
    for topic, playbook in PLAYBOOKS.items():
        if any(token in text for token in playbook['signals']):
            return topic
    return 'unknown'


def from_report(document):
    signals = [f.get('signal', f.get('message', 'unknown')) for f in document.get('findings', [])]
    signals += [c.get('check', 'unknown') for c in document.get('checks', []) if c.get('status') in {'FAIL', 'UNKNOWN', 'WARN'}]
    for pod in document.get('pods', []):
        if pod.get('phase') == 'Pending':
            signals.append('Pending')
        signals.extend(c['reason'] for c in pod.get('containers', []) if c.get('reason'))
    signals += [e.get('reason', 'unknown') for e in document.get('events', []) if e.get('type') == 'Warning']
    signals += [e.get('event') for e in document.get('entries', []) if e.get('event') in {'outcome_unknown', 'verification_timeout'}]
    if document.get('kind') == 'repair-dry-run' and document.get('result') != 'SERVER_ACCEPTED':
        signals.append('recovery')
    if document.get('unavailable'):
        signals.append('toolkit-error')
    topics = list(dict.fromkeys(topic_for(s) for s in signals))
    return topics or ['unknown']


def build(topics, example=False):
    return {'schema_version': 1, 'kind': 'troubleshooting-suggestions', 'example': bool(example),
            'suggestions': [{'topic': topic, 'possible_causes': PLAYBOOKS[topic]['causes'],
                             'steps': PLAYBOOKS[topic]['steps'], 'verify': PLAYBOOKS[topic]['verify']} for topic in topics],
            'limitations': ['Suggestions are rule-based investigation paths, not proven root causes or guaranteed fixes.',
                            'No command, network query, repair, permission grant or retry is executed.',
                            'Old events and incomplete snapshots can mislead; verify current scope and state.',
                            'If investigation stalls or a mutation outcome is unknown, escalate with private evidence; do not bypass repair guards.']}


def render(document):
    lines = ['Troubleshooting suggestions — review evidence before changing anything.']
    if document['example']:
        lines.append('ILLUSTRATIVE example; not real cluster evidence.')
    for suggestion in document['suggestions']:
        lines += ['', 'Issue area: ' + suggestion['topic'], 'Possible causes: ' + ' '.join(suggestion['possible_causes'])]
        lines += [str(i) + '. ' + step for i, step in enumerate(suggestion['steps'], 1)]
        lines.append('Verify: ' + suggestion['verify'])
    lines += ['', *['NOTE: ' + note for note in document['limitations']]]
    return '\n'.join(lines)


def failure_hint(arguments, code):
    if code not in {1, 2} or not arguments or arguments[0] not in {
            'diagnose', 'release-check', 'manifest-check', 'preflight', 'incident', 'bundle',
            'drift', 'recover', 'repair', 'repair-dry-run', 'watch-recovery', 'policy', 'demo'}:
        return None
    command = ['devops-toolkit', 'suggest', '--issue',
               'recovery' if arguments[0] in {'recover', 'repair', 'repair-dry-run', 'watch-recovery', 'policy'} else 'toolkit-error']
    if arguments[0] in {'diagnose', 'release-check', 'manifest-check'} and '--output' in arguments:
        index = arguments.index('--output')
        if index + 1 < len(arguments) and not any(ord(c) < 32 or ord(c) == 127 for c in arguments[index + 1]):
            # The suggested input may not exist when collection failed; never imply it was saved.
            command = ['devops-toolkit', 'suggest', '--report', arguments[index + 1]]
            return 'If a JSON report was saved, review next steps with: ' + shlex.join(command)
    return 'For suggested checks and resolution steps: ' + shlex.join(command)


def main(argv=None):
    from .cli import write_private
    parser = argparse.ArgumentParser(prog='devops-toolkit suggest')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--issue', help='Symptom or topic, e.g. CrashLoopBackOff, Pending, storage, stuck')
    source.add_argument('--report', help='Existing toolkit JSON evidence; processed offline')
    parser.add_argument('--list', action='store_true', help='List supported issue areas')
    parser.add_argument('--format', choices=['text', 'json'], default='text')
    parser.add_argument('--output', help='New private JSON suggestion file; parent must exist')
    args = parser.parse_args(argv)
    if args.list or not (args.issue or args.report):
        print('Issue areas: ' + ', '.join(PLAYBOOKS))
        return 0
    try:
        example = False
        if args.report:
            from .report import load
            evidence = load(args.report)
            topics, example = from_report(evidence), evidence.get('example', False)
        else:
            topics = [topic_for(args.issue)]
        document = build(topics, example)
        if args.output:
            write_private(Path(args.output), json.dumps(document, indent=2) + '\n')
        print(json.dumps(document, indent=2) if args.format == 'json' else render(document))
        return 0  # Suggestions produced; never a health/recovery result.
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        print('Cannot read evidence/save suggestions. Use a supported toolkit JSON report and a new output path. For general steps: devops-toolkit suggest --issue stuck', file=sys.stderr)
        return 2
