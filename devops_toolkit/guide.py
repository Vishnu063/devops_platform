"""Interactive command planner. Never executes generated commands."""
import argparse
import shlex
import sys

TASKS = {
    'offline': ('Check a manifest without cluster access', ['manifest-check', '--format', 'text', '--file', 'FILE', '--namespace', 'NAMESPACE']),
    'diagnose': ('Read symptoms in one namespace', ['diagnose', '--format', 'text', '--context', 'CONTEXT', '--namespace', 'NAMESPACE']),
    'bundle': ('Collect private evidence for one Deployment', ['bundle', '--context', 'CONTEXT', '--namespace', 'NAMESPACE', '--deployment', 'DEPLOYMENT', '--output', 'OUTPUT']),
    'release': ('Check release risks without deploying', ['release-check', '--format', 'text', '--context', 'CONTEXT', '--namespace', 'NAMESPACE', '--deployment', 'DEPLOYMENT', '--service', 'SERVICE', '--file', 'FILE']),
    'report': ('Create a local HTML report from saved JSON', ['report', 'FILE', '--format', 'html', '--output', 'OUTPUT']),
    'handover': ('Create a ticket or shift handover draft', ['handover', 'FILE', '--output', 'OUTPUT']),
    'gitops': ('Propose a source-manifest image change for review', ['gitops-propose', '--before', 'BEFORE', '--after', 'AFTER', '--path', 'SOURCE_PATH', '--output', 'OUTPUT']),
}
PROMPTS = {'FILE': 'Input file', 'CONTEXT': 'Explicit kubectl context', 'NAMESPACE': 'Namespace',
           'DEPLOYMENT': 'Deployment name', 'SERVICE': 'Service name', 'OUTPUT': 'New output path (parent must exist)',
           'BEFORE': 'Original source manifest file', 'AFTER': 'Reviewed candidate manifest file',
           'SOURCE_PATH': 'Repository-relative path of original manifest'}


def plan(task, values):
    return ['devops-toolkit', *[values.get(part, part) for part in TASKS[task][1]]]


def main(argv=None):
    parser = argparse.ArgumentParser(prog='devops-toolkit guide')
    parser.add_argument('--task', choices=TASKS)
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        print('Guide needs an interactive terminal. Use --help on the command you need.', file=sys.stderr)
        return 2
    try:
        task = args.task
        if task is None:
            for index, (key, (label, _)) in enumerate(TASKS.items(), 1):
                print(str(index) + '. ' + label)
            choice = input('Choose 1..7: ').strip()
            if choice not in [str(i) for i in range(1, len(TASKS) + 1)]:
                raise ValueError('Invalid choice')
            task = list(TASKS)[int(choice) - 1]
        values = {}
        for part in TASKS[task][1]:
            if part in PROMPTS and part not in values:
                value = input(PROMPTS[part] + ': ').strip()
                if not value or value.startswith('-') or any(ord(c) < 32 or ord(c) == 127 for c in value):
                    raise ValueError('Use a nonempty value without control characters or a leading dash')
                values[part] = value
        print('\nSuggested command (POSIX shell):\n' + shlex.join(plan(task, values)))
        print('Review it before copying. Nothing was executed. No repair or deployment is started by this guide.')
        if task in {'diagnose', 'bundle', 'release'}:
            print('Running that command contacts your explicitly selected cluster; it does not repair it.')
        if task in {'report', 'handover', 'bundle'}:
            print('Reports may identify internal resources. Review privately before sharing.')
        return 0
    except (EOFError, KeyboardInterrupt, ValueError):
        print('\nGuide stopped; no command was executed.', file=sys.stderr)
        return 2
