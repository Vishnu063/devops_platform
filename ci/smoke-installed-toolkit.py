"""Exercise the installed console entry point away from the source checkout."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('executable', help='Absolute path to installed devops-toolkit')
args = parser.parse_args()
executable = str(Path(args.executable).resolve(strict=True))
with tempfile.TemporaryDirectory(prefix='toolkit-smoke-') as directory:
    def run(*arguments, expected=0):
        result = subprocess.run([executable, *arguments], cwd=directory, capture_output=True,
                                text=True, timeout=30, check=False)
        if result.returncode != expected:
            raise RuntimeError('Installed command failed: ' + arguments[0] + '; exit ' + str(result.returncode))
        return result.stdout
    assert '0.3.0.dev0' in run('--version')
    run('doctor')
    run('guide', expected=2)
    run('example', '--scenario', 'crash', '--output', 'example.json')
    run('suggest', '--report', 'example.json', '--output', 'suggestions.json')
    run('report', 'example.json', '--output', 'example.html')
    run('handover', 'example.json', '--output', 'handover.md')
    document = json.loads((Path(directory)/'suggestions.json').read_text())
    assert document['example'] is True and document['suggestions'][0]['topic'] == 'crash'
    assert 'ILLUSTRATIVE' in (Path(directory)/'example.html').read_text()
    assert 'TO COMPLETE' in (Path(directory)/'handover.md').read_text()
print('Installed CLI smoke passed: version, doctor, guide boundary, example, suggestions, HTML and handover. No cluster access.')
