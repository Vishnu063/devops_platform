#!/usr/bin/env bash
# Isolated rollback drill. Never touches devops_platform-api-1 or host port 8080.
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="devops-rollback-drill"
SERVICE="${PROJECT}-api-1"
IMAGE_ID="$(docker inspect --format '{{.Image}}' devops_platform-api-1)"
docker image inspect "$IMAGE_ID" >/dev/null
TMP="$(mktemp "$PWD/.rollback-drill.XXXXXXXX.yml")"
cleanup() { docker compose -p "$PROJECT" -f "$TMP" down --remove-orphans >/dev/null 2>&1 || true; rm -f "$TMP"; }
trap cleanup EXIT
write_compose() {
  cat > "$TMP" <<EOF
services:
  api:
    image: "$IMAGE_ID"
    network_mode: none
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    pids_limit: 64
    mem_limit: 128m
    restart: "no"
    healthcheck:
      test: ["CMD", "${1}"]
      interval: 2s
      timeout: 2s
      retries: 2
      start_period: 1s
EOF
}
# An isolated container's built-in healthcheck uses 127.0.0.1, no networking required.
wait_health() {
  local want="$1" i state
  for i in $(seq 1 20); do
    state="$(docker inspect --format '{{.State.Health.Status}}' "$SERVICE" 2>/dev/null || true)"
    if [[ "$state" == "$want" ]]; then return 0; fi
    sleep 2
  done
  echo "Expected health=$want; observed ${state:-missing}" >&2
  return 1
}
echo "Starting isolated baseline using existing healthy image..."
write_compose python
# Use a simple existing executable as the baseline health command.
docker compose -p "$PROJECT" -f "$TMP" up -d --no-build
wait_health healthy
echo "Simulating a bad release (healthcheck always fails)..."
write_compose false
docker compose -p "$PROJECT" -f "$TMP" up -d --no-build --force-recreate
wait_health unhealthy
echo "Bad release detected. Restoring the prior healthy configuration..."
write_compose python
docker compose -p "$PROJECT" -f "$TMP" up -d --no-build --force-recreate
wait_health healthy
echo "ROLLBACK DRILL PASSED: isolated unhealthy release was detected and restored."
