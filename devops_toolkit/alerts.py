"""Opt-in outcome notifications. Destinations and secrets stay outside reports."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def prepare(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise ValueError('Alert config too large')
    config = json.loads(raw)
    if set(config) != {'provider', 'url_env'} or config['provider'] not in {'slack', 'teams', 'webhook'}:
        raise ValueError('Use provider and url_env only')
    if not isinstance(config['url_env'], str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', config['url_env']):
        raise ValueError('Invalid environment variable name')
    url = os.environ.get(config['url_env'], '')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('An explicit HTTPS webhook environment variable is required')
    return {'provider': config['provider'], 'url': url}


def outcome(command, code, args):
    result = 'completed' if code == 0 else 'needs_attention' if code == 1 else 'failed_or_unknown'
    if command in {'release-check', 'diagnose'} and code in {1, 2}:
        result = 'needs_attention'
    if '--execute' not in args and command in {'recover', 'repair', 'watch-recovery'}:
        result = 'preview_completed' if code == 0 else result
    if '--execute' in args and '--audit' in args:
        try:
            path = Path(args[args.index('--audit') + 1])
            if path.stat().st_size <= 1024 * 1024:
                events = [json.loads(line).get('event') for line in path.read_text().splitlines()]
                if code == 0 and any(e in {'deployment_ready', 'readiness_confirmed'} for e in events):
                    result = 'recovery_succeeded'
                elif code == 0 and not events:
                    result = 'completed_without_repair'
        except (OSError, ValueError, IndexError, TypeError, AttributeError):
            pass
    return {'event_id': uuid.uuid4().hex, 'time': datetime.now(timezone.utc).isoformat(),
            'tool': 'devops-platform-toolkit', 'command': command, 'result': result, 'exit_code': code}


def send(config, event):
    # Only the fixed outcome schema leaves the machine: no target, logs, paths, UID,
    # policy contents, environment values, webhook URL or raw command output.
    safe = {k: event[k] for k in ('event_id', 'time', 'tool', 'command', 'result', 'exit_code')}
    text = 'DevOps toolkit: ' + safe['command'] + ' — ' + safe['result'] + ' (exit ' + str(safe['exit_code']) + '). Event ' + safe['event_id']
    if config['provider'] == 'slack':
        payload = {'text': text}
    elif config['provider'] == 'teams':
        payload = {'type': 'message', 'attachments': [{'contentType': 'application/vnd.microsoft.card.adaptive',
                   'content': {'type': 'AdaptiveCard', 'version': '1.2', 'body': [
                       {'type': 'TextBlock', 'text': text, 'wrap': True}]}}]}
    else:
        payload = safe
    request = urllib.request.Request(config['url'], data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                raise ValueError('Webhook rejected notification')
    except (OSError, urllib.error.URLError, ValueError) as error:
        # Never expose URLs: many webhook URLs contain credentials.
        raise ValueError('Alert delivery failed; operation outcome is unchanged') from error


def invoke(arguments, runner):
    import sys
    args = list(arguments)
    if '--notify-config' not in args:
        return runner(args)
    try:
        index = args.index('--notify-config')
        if args.count('--notify-config') != 1 or index + 1 >= len(args):
            raise ValueError('Use one --notify-config path')
        path = args[index + 1]
        del args[index:index + 2]
        if not args or args[0] not in {'recover', 'repair', 'watch-recovery', 'release-check', 'diagnose'}:
            raise ValueError('Notifications are supported only for operational commands')
        config = prepare(path)  # Validate before allowing an operation to start.
    except (OSError, ValueError, TypeError, KeyError):
        print('Invalid notification configuration; operation was not started.', file=sys.stderr)
        return 2
    try:
        code = runner(args)
    except KeyboardInterrupt:
        code = 130
    if any(a in {'-h', '--help'} for a in args):
        return code
    event = outcome(args[0], code, args)
    try:
        send(config, event)
        print('Outcome notification delivered. Event ' + event['event_id'], file=sys.stderr)
    except ValueError:
        print('Outcome notification failed. Event ' + event['event_id'] + '. Inspect operation output/audit; no operation was retried.', file=sys.stderr)
        return code if code else 3
    return code
