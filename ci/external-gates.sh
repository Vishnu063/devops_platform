#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ci/tool-images.env
: "${SONAR_TOKEN:?Set SONAR_TOKEN}"
: "${SONAR_HOST_URL:?Set SONAR_HOST_URL}"
: "${SNYK_TOKEN:?Set SNYK_TOKEN}"
[[ "$SONAR_HOST_URL" == https://* ]] || { echo "SonarQube must use HTTPS"; exit 1; }
sha256sum --check reports/image-archive.sha256
# Both scanners analyze the same source/image artifacts that will be published.
docker run --rm --user "$(id -u):$(id -g)" -e SONAR_TOKEN -e SONAR_HOST_URL \
  -e SONAR_USER_HOME=/tmp/.sonar \
  -v "$PWD:/usr/src" "$SONAR_IMAGE" -Dsonar.qualitygate.wait=true
docker run --rm -e SNYK_TOKEN -v "$PWD:/project:ro" -w /project "$SNYK_IMAGE" \
  snyk container test docker-archive:platform-image.tar --severity-threshold=high
