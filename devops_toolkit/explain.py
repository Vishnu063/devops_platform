"""Evidence and bounded next steps shared by terminal and saved reports."""
import re
import shlex


def next_step(report, finding):
    key = str(finding.get('check', finding.get('signal', ''))).lower()
    action = finding.get('next_action')
    if not action:
        if any(word in key for word in ['image', 'registry']):
            action = 'Review the intended image digest and registry access; do not substitute an unreviewed image.'
        elif any(word in key for word in ['probe', 'unhealthy', 'notready']):
            action = 'Check probe path, port and timing against the application; retain health checks.'
        elif any(word in key for word in ['resource', 'capacity', 'limit', 'scheduling']):
            action = 'Review measured usage, resource budgets and scheduling constraints before changing requests or limits.'
        elif 'selector' in key or 'service' in key:
            action = 'Compare Service selectors, intended pod labels and declared ports; then verify endpoints and traffic separately.'
        elif 'reference' in key:
            action = 'Verify required configuration objects and keys without copying their values into a report.'
        elif 'recovery' in key or 'gitops' in key:
            action = 'Review the approved recovery scope and owning controller. GitOps changes need source review.'
        else:
            action = 'Review this observation with the workload owner and the documented check limits before making changes.'
    context, namespace = report.get('context'), report.get('namespace')
    resource = finding.get('resource', '')
    command = None
    if (isinstance(context, str) and context and not context.startswith('-') and
            isinstance(namespace, str) and re.fullmatch(r'[a-z0-9][-a-z0-9]*', namespace) and
            isinstance(resource, str) and re.fullmatch(r'(pods|deployments)/[a-z0-9][a-z0-9.-]*', resource)):
        command = shlex.join(['kubectl', '--context', context, '--namespace', namespace,
                              '--request-timeout=10s', 'get', resource, '-o', 'wide'])
    return {'next_step': action, 'read_only_command': command,
            'uncertainty': 'Observed symptoms/configuration do not prove root cause or successful recovery.'}
