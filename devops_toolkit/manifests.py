"""Bounded JSON/YAML loading and explicit local Helm rendering; no deployment."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

MAX_BYTES = 8 * 1024 * 1024


def normalize(documents):
    objects, identities = [], set()
    def add(obj, depth=0):
        if obj is None:
            return
        if not isinstance(obj, dict) or depth > 10:
            raise ValueError('Expected Kubernetes object documents')
        if obj.get('kind') == 'List':
            if not isinstance(obj.get('items'), list):
                raise ValueError('Invalid Kubernetes List')
            for child in obj['items']:
                add(child, depth + 1)
            return
        metadata = obj.get('metadata', {})
        if any(not isinstance(v, str) or not v for v in (obj.get('apiVersion'), obj.get('kind'), metadata.get('name'))):
            raise ValueError('Each object needs apiVersion, kind and metadata.name')
        identity = (obj['apiVersion'], obj['kind'], metadata.get('namespace', ''), metadata['name'])
        if identity in identities:
            raise ValueError('Duplicate object identity')
        identities.add(identity)
        objects.append(obj)
        if len(objects) > 2000:
            raise ValueError('Too many objects')
    for document in documents:
        add(document)
    if not objects:
        raise ValueError('No Kubernetes objects')
    return {'apiVersion': 'v1', 'kind': 'List', 'items': objects}


def parse(text):
    if len(text.encode()) > MAX_BYTES:
        raise ValueError('Manifest input too large')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    if text.lstrip().startswith(('{', '[')):
        try:
            return normalize([json.loads(text, object_pairs_hook=pairs)])
        except RecursionError as error:
            raise ValueError('Manifest nesting is too deep') from error
        except json.JSONDecodeError:
            pass  # Flow-style YAML may also start with a brace.
    try:
        import yaml
    except ImportError as error:
        raise ValueError('Install the optional YAML extra: pip install ".[yaml]"') from error
    class StrictLoader(yaml.SafeLoader):
        count, depth = 0, 0
        def compose_node(self, parent, index):
            if self.check_event(yaml.AliasEvent):
                raise ValueError('YAML aliases are not supported; expand them first')
            self.count += 1
            self.depth += 1
            if self.count > 100000 or self.depth > 100:
                raise ValueError('YAML input too complex')
            try:
                return super().compose_node(parent, index)
            finally:
                self.depth -= 1
        def construct_mapping(self, node, deep=False):
            self.flatten_mapping(node)
            result = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str) or key in result:
                    raise ValueError('YAML keys must be unique strings')
                result[key] = self.construct_object(value_node, deep=deep)
            return result
    try:
        result = normalize(list(yaml.load_all(text, Loader=StrictLoader)))
        # Kubernetes JSON does not contain YAML-specific date/set/tag values.
        json.dumps(result)
        return result
    except (yaml.YAMLError, TypeError) as error:
        raise ValueError('Use plain Kubernetes YAML; quote dates and expand special types') from error


def load(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Manifest input too large')
    return parse(raw.decode('utf-8'))


def source_arguments(parser, required=False):
    source = parser.add_mutually_exclusive_group(required=required)
    source.add_argument('--file', help='Kubernetes JSON/List or multi-document YAML')
    source.add_argument('--chart', help='Trusted local Helm chart directory; rendering only')
    parser.add_argument('--release', default='platform', help='Local Helm rendering release name')
    parser.add_argument('--values', action='append', default=[], help='Local Helm values file; repeatable')
    parser.add_argument('--set', dest='helm_set', action='append', default=[], help='Helm key=value; repeatable, avoid secrets on command lines')


def source_document(args):
    if getattr(args, '_manifest_document', None) is not None:
        return args._manifest_document
    if getattr(args, 'file', None):
        if getattr(args, 'values', []) or getattr(args, 'helm_set', []):
            raise ValueError('--values/--set require --chart')
        result = load(args.file)
    elif getattr(args, 'chart', None):
        chart = Path(args.chart).resolve()
        if not chart.is_dir() or not (chart/'Chart.yaml').is_file():
            raise ValueError('Use a local chart with Chart.yaml')
        if not re.fullmatch(r'[a-z0-9](?:[-a-z0-9]*[a-z0-9])?', args.release) or len(args.release) > 53:
            raise ValueError('Invalid Helm release name')
        command = ['helm', 'template', args.release, str(chart), '--namespace', args.namespace]
        for path in getattr(args, 'values', []):
            if not Path(path).is_file():
                raise ValueError('Values file unavailable')
            command.extend(['--values', str(Path(path).resolve())])
        for setting in getattr(args, 'helm_set', []):
            if '=' not in setting or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.\[\]\\-]*', setting.split('=', 1)[0]):
                raise ValueError('Use explicit Helm key=value settings')
            command.extend(['--set', setting])
        with tempfile.TemporaryDirectory(prefix='devops-helm-') as plugins:
            try:
                output = subprocess.run(command, capture_output=True, timeout=60, check=False,
                                        env={**os.environ, 'HELM_PLUGINS': plugins, 'HELM_NO_PLUGINS': '1'})
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ValueError('Helm unavailable or rendering timed out') from error
        if output.returncode or len(output.stdout) > MAX_BYTES:
            raise ValueError('Helm render failed or exceeded input limit; inspect chart locally')
        result = parse(output.stdout.decode('utf-8'))
    else:
        raise ValueError('Supply --file or --chart')
    args._manifest_document = result  # Render once so random template functions cannot change the candidate between checks.
    return result
