"""Emergency-stop checks shared by direct repair paths."""
import os


def ensure_enabled(namespace, expected_uid=None):
    if os.environ.get('DEVOPS_TOOLKIT_DISABLE_REPAIRS', '').lower() in {'1', 'true', 'yes'}:
        raise ValueError('Repairs disabled by process environment')
    metadata = namespace['metadata']
    if expected_uid is not None and metadata['uid'] != expected_uid:
        raise ValueError('Namespace identity changed')
    value = metadata.get('annotations', {}).get('devops-platform.io/repairs-paused')
    if value not in (None, 'false'):
        raise ValueError('Namespace repairs paused or stop value invalid')
