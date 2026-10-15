"""Local review bundle for source-manifest image changes. No Git/network/apply."""
import argparse
import copy
import difflib
import json
from pathlib import Path, PurePosixPath
import re
import sys

from .manifests import parse

IMAGE = r'[A-Za-z0-9._:/-]+@sha256:[a-f0-9]{64}'
IMAGE_LINE = re.compile(r'\s*(?:image:\s*[\"\']?[A-Za-z0-9._:/@-]+[\"\']?|"image"\s*:\s*"[A-Za-z0-9._:/@-]+",?)\s*')


def read(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Source input too large')
    return raw.decode('utf-8')


def proposal(before, after, source_path, namespace):
    path = PurePosixPath(source_path)
    if path.is_absolute() or '..' in path.parts or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./-]*', source_path) or source_path.endswith('/'):
        raise ValueError('Use a simple repository-relative source path')
    left, right = parse(before), parse(after)
    def objects(document):
        result = {}
        for obj in document['items']:
            if obj['kind'] != 'Deployment' or obj['apiVersion'] != 'apps/v1':
                raise ValueError('Only source apps/v1 Deployments supported')
            key = (obj['metadata'].get('namespace', namespace), obj['metadata']['name'])
            if key in result:
                raise ValueError('Duplicate target')
            result[key] = obj
        return result
    old, new = objects(left), objects(right)
    if old.keys() != new.keys() or not old:
        raise ValueError('Source target set changed')
    changes = []
    for key, original in old.items():
        candidate = copy.deepcopy(new[key])
        previous = original['spec']['template']['spec']['containers']
        current = candidate['spec']['template']['spec']['containers']
        if len(previous) != len(current) or not current:
            raise ValueError('Container set changed')
        names = [c['name'] for c in current]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate container')
        for a, b in zip(previous, current):
            if a['name'] != b['name']:
                raise ValueError('Container identity/order changed')
            if a['image'] != b['image']:
                if not re.fullmatch(IMAGE, b['image']):
                    raise ValueError('New image requires an explicit digest')
                changes.append({'namespace': key[0], 'deployment': key[1], 'container': b['name']})
                b['image'] = a['image']
        if candidate != original:
            raise ValueError('Only regular-container image changes supported')
    if not changes:
        raise ValueError('No image change')
    # Zero context avoids exporting adjacent env values or other arbitrary fields.
    lines = list(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                     fromfile='a/' + source_path, tofile='b/' + source_path, n=0))
    for line in lines[2:]:
        if line.startswith(('+', '-')) and not IMAGE_LINE.fullmatch(line[1:].rstrip('\n')):
            raise ValueError('Text changes must be image-only lines without comments')
    if not before.endswith('\n') or not after.endswith('\n'):
        raise ValueError('Source files must end with a newline')
    return ''.join(lines), changes


def main(argv=None):
    from .cli import write_private
    parser = argparse.ArgumentParser(prog='devops-toolkit gitops-propose')
    parser.add_argument('--before', required=True, help='Original source manifest, not kubectl output or a Helm render')
    parser.add_argument('--after', required=True, help='Reviewed source candidate with image-only edits')
    parser.add_argument('--path', required=True, help='Repository-relative path of the original source file')
    parser.add_argument('--namespace', default='platform', help='Effective namespace for omitted metadata.namespace')
    parser.add_argument('--output', required=True, help='New private proposal directory')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?', args.namespace):
        parser.error('Use a valid effective namespace')
    try:
        patch, changes = proposal(read(args.before), read(args.after), args.path, args.namespace)
        directory = Path(args.output)
        directory.mkdir(mode=0o700, exist_ok=False)
        write_private(directory / 'change.patch', patch)
        review = {'schema_version': 1, 'kind': 'gitops-source-proposal', 'source_path': args.path,
                  'changes': changes, 'approval': 'REQUIRED', 'execution': 'NONE',
                  'limitations': ['Local review draft only; no Git commit, PR, API call, apply or reconciliation.',
                                  'Image existence, compatibility, signatures, architecture, live ownership and runtime health are not verified.',
                                  'Only plain source Deployment manifests with isolated regular-container image lines are supported.',
                                  'Helm values/templates and Kustomize overlays need a separately reviewed source edit.']}
        write_private(directory / 'proposal.json', json.dumps(review, indent=2, ensure_ascii=True) + '\n')
        write_private(directory / 'REVIEW.md', '# GitOps image change proposal\n\n'
                      'Approval required. No cluster or Git changes were made.\n\n'
                      '1. Verify the original file matches the target Git branch and this is the actual controller source.\n'
                      '2. Review change.patch privately. It has zero context to exclude unrelated configuration; do not apply it blindly.\n'
                      '3. Verify image availability, signature, platform, compatibility and rollback constraints.\n'
                      '4. Create your normal reviewed source PR. Keep Helm/Kustomize changes in their actual source.\n'
                      '5. Use your existing approval and Argo CD/Flux reconciliation process. Verify rollout and application health.\n\n'
                      'The proposal is not a repair approval policy and cannot bypass direct-repair ownership guards.\n')
        print('Saved a private GitOps review proposal. No commit, PR, cluster change or reconciliation was performed.')
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        print('Proposal refused/incomplete: use matching plain Deployment source manifests, image-only lines, digest-pinned candidates and a new output directory. Review any partial output privately.', file=sys.stderr)
        return 2
