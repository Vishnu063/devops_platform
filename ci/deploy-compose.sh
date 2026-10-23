#!/usr/bin/env bash
# Deploy the CI-built image to the existing single-host Docker Compose service.
# The first deployment must be explicitly approved in Jenkins.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${GIT_SHA:?Jenkins must provide the validated commit SHA}"
[[ "$GIT_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid GIT_SHA"; exit 1; }
IMAGE="ghcr.io/vishnu063/devops_platform:$GIT_SHA"
SERVICE="devops_platform-api-1"
PROJECT="devops_platform"
docker image inspect "$IMAGE" >/dev/null
# Refuse to take over an unknown service. The current app must already be healthy.
docker inspect "$SERVICE" >/dev/null
BEFORE_ID="$(docker inspect --format '{{.Image}}' "$SERVICE")"
BEFORE_STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$SERVICE")"
[[ "$BEFORE_STATUS" == healthy ]] || { echo "Existing service is not healthy; refusing deployment."; exit 1; }
# Preserve original image by immutable local image ID; no pull/login required.
TMP_OVERRIDE="$(mktemp "$PWD/.compose-cd.XXXXXXXX.yml")"
cleanup() { rm -f "$TMP_OVERRIDE"; }
trap cleanup EXIT
write_override() {
  cat > "$TMP_OVERRIDE" <<EOF
services:
  api:
    image: "$1"
EOF
}
compose() { docker compose -p "$PROJECT" -f compose.yml -f "$TMP_OVERRIDE" "$@"; }
rollback() {
  echo "Deployment failed; rolling back the previous image."
  write_override "$BEFORE_ID"
  compose up -d --no-build --force-recreate api || { echo "Rollback command failed; manual recovery required."; return 1; }
  for attempt in $(seq 1 30); do
    if [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$SERVICE" 2>/dev/null || true)" == healthy ]] && curl -fsS --max-time 3 http://127.0.0.1:8080/health/live >/dev/null; then
      echo "Rollback health verified."
      return 0
    fi
    sleep 2
  done
  echo "Rollback health not verified; manual recovery required."
  return 1
}
echo "Deploying validated image $IMAGE to $SERVICE"
write_override "$IMAGE"
if ! compose up -d --no-build --force-recreate api; then
  rollback || true
  exit 1
fi
EXPECTED_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
for attempt in $(seq 1 30); do
  CURRENT_ID="$(docker inspect --format '{{.Image}}' "$SERVICE" 2>/dev/null || true)"
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$SERVICE" 2>/dev/null || true)"
  if [[ "$CURRENT_ID" == "$EXPECTED_ID" && "$STATUS" == healthy ]] && curl -fsS --max-time 3 http://127.0.0.1:8080/health/live >/dev/null; then
    echo "Deployment verified: image ID matches, Docker health=healthy, HTTP /health/live=200."
    exit 0
  fi
  sleep 2
done
echo "New release did not become healthy."
rollback || true
exit 1
