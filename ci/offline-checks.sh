#!/usr/bin/env bash
# No kubeconfig, cluster access, image build, publication or repair in this script.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
source ci/tool-images.env
TOOLKIT_PYTHON="${TOOLKIT_PYTHON:-python3}"
mkdir -p reports
# Refuse accidental replacement of evidence from a previous invocation.
if [[ -e reports/offline-check.json || -e reports/offline-summary.md ]]; then
  echo 'Use a clean CI workspace or move previous offline evidence first.' >&2
  exit 2
fi
TOOLKIT_RENDER_DIR="$(mktemp -d)"
trap 'rm -rf -- "$TOOLKIT_RENDER_DIR"' EXIT
for TOOLKIT_TEST_PATTERN in test_toolkit.py test_compare.py test_recovery.py test_watch_recovery.py test_repair.py test_demo.py test_product.py test_ci_tools.py test_usability.py test_suggestions.py; do
  "$TOOLKIT_PYTHON" -m unittest discover -s tests -p "$TOOLKIT_TEST_PATTERN" -v
done
# Chart rendering is isolated from the network. The pinned tool image may need
# to be downloaded by Docker before the isolated container starts.
docker run --rm --network none -v "$PWD:/src:ro" -w /src "$HELM_IMAGE" \
  template platform charts/platform --namespace platform -f ci/offline-values.yaml \
  > "$TOOLKIT_RENDER_DIR/rendered.yaml"
TOOLKIT_CHECK_CODE=0
"$TOOLKIT_PYTHON" -m devops_toolkit manifest-check \
  --file "$TOOLKIT_RENDER_DIR/rendered.yaml" --namespace platform \
  --warnings-as-errors --output reports/offline-check.json > /dev/null || TOOLKIT_CHECK_CODE=$?
"$TOOLKIT_PYTHON" - <<'PY'
import json
from pathlib import Path
path = Path('reports/offline-check.json')
if path.exists():
    report = json.loads(path.read_text())
    counts = {key: sum(c['status'] == key for c in report['checks']) for key in ('PASS', 'FAIL', 'WARN', 'NOTE')}
    text = '# Toolkit configuration check\n\n'
    text += 'Configuration: **' + report['configuration_decision'] + '**\n\n'
    text += 'Live deployment readiness: **NOT ASSESSED OFFLINE**\n\n'
    text += 'Gate policy: configuration warnings also fail this repository check.\n\n'
    text += '| PASS | FAIL | WARN | NOTE |\n| --- | --- | --- | --- |\n'
    text += '| ' + ' | '.join(str(counts[k]) for k in ('PASS', 'FAIL', 'WARN', 'NOTE')) + ' |\n\n'
    text += 'The render used an explicit placeholder digest. No image existence, cluster, Secret values, capacity, admission or traffic was checked.\n'
    text += 'See the configuration report artifact. Raw rendered YAML is temporary and is not uploaded.\n'
else:
    text = '# Toolkit configuration check\n\nNo complete report was produced. Inspect the failed job step.\n'
Path('reports/offline-summary.md').write_text(text)
PY
exit "$TOOLKIT_CHECK_CODE"
