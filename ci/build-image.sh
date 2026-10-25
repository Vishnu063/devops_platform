#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ci/tool-images.env
[[ "$GIT_SHA" =~ ^[a-f0-9]{40}$ ]]
IMAGE="ghcr.io/vishnu063/devops_platform:$GIT_SHA"
mkdir -p reports
docker build --platform linux/amd64 --build-arg APP_VERSION="$GIT_SHA" -t "$IMAGE" .
docker save "$IMAGE" -o platform-image.tar
sha256sum platform-image.tar > reports/image-archive.sha256
docker run --rm -v "$PWD:/src:ro" -v "$PWD/reports:/reports" "$TRIVY_IMAGE" \
  image --input /src/platform-image.tar --scanners vuln --severity HIGH,CRITICAL \
  --ignore-unfixed --exit-code 1 --format json --output /reports/trivy.json
docker run --rm -v "$PWD:/src:ro" -v "$PWD/reports:/reports" "$TRIVY_IMAGE" \
  image --input /src/platform-image.tar --format cyclonedx --output /reports/sbom.json
docker image inspect --format '{{.Id}}' "$IMAGE" > reports/image-id.txt
