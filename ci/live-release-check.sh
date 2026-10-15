#!/usr/bin/env bash
# Trusted runner only. No repair, apply, delete or automatic deployment.
# Reports stay in an operator-specified private directory, outside the SCM workspace.
set -euo pipefail
umask 077
: "${TOOLKIT_CONTEXT:?Set the explicitly approved context}"
: "${TOOLKIT_NAMESPACE:?Set the target namespace}"
: "${TOOLKIT_DEPLOYMENT:?Set the target Deployment}"
: "${TOOLKIT_SERVICE:?Set the intended Service}"
: "${TOOLKIT_CANDIDATE:?Set a reviewed rendered YAML/JSON candidate path}"
: "${TOOLKIT_PRIVATE_REPORT:?Set a NEW private JSON output path outside CI artifacts}"
TOOLKIT_PYTHON="${TOOLKIT_PYTHON:-python3}"
# Validate privacy before contacting the cluster. The output directory must exist
# outside the workspace and be accessible only by its owner.
"$TOOLKIT_PYTHON" - <<'PYCODE'
import os
from pathlib import Path
try:
    output = Path(os.environ['TOOLKIT_PRIVATE_REPORT'])
    workspace = Path(os.environ.get('WORKSPACE', str(Path.cwd()))).absolute()
    if not output.is_absolute() or output.absolute().is_relative_to(workspace) or output.resolve().is_relative_to(workspace.resolve()):
        raise SystemExit('Use an absolute private report path outside the CI workspace')
    if output.exists() or not output.parent.is_dir() or output.parent.stat().st_mode & 0o077:
        raise SystemExit('Use a new report file in an existing owner-only directory')
except OSError:
    raise SystemExit('Private report destination could not be validated')
PYCODE
TOOLKIT_LIVE_ARGS=(release-check --context "$TOOLKIT_CONTEXT" --namespace "$TOOLKIT_NAMESPACE"
  --deployment "$TOOLKIT_DEPLOYMENT" --service "$TOOLKIT_SERVICE"
  --file "$TOOLKIT_CANDIDATE" --output "$TOOLKIT_PRIVATE_REPORT")
if [[ -n "${TOOLKIT_POLICY:-}" ]]; then
  TOOLKIT_LIVE_ARGS+=(--policy "$TOOLKIT_POLICY")
fi
TOOLKIT_LIVE_CODE=0
# Suppress resource identities/details in public CI stdout; never auto-upload.
"$TOOLKIT_PYTHON" -m devops_toolkit "${TOOLKIT_LIVE_ARGS[@]}" > /dev/null || TOOLKIT_LIVE_CODE=$?
case "$TOOLKIT_LIVE_CODE" in
  0) echo 'Live release-check: implemented checks passed. This is not deployment approval.' ;;
  1) echo 'Live release-check: BLOCKED. Inspect the private report.' ;;
  2) echo 'Live release-check: NEEDS REVIEW or incomplete. Inspect private evidence and access.' ;;
  *) echo 'Live release-check: unexpected failure. Inspect the trusted runner.' ;;
esac
exit "$TOOLKIT_LIVE_CODE"
