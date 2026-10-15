#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ci/tool-images.env
if [[ "$(git rev-parse --is-shallow-repository)" != false ]]; then
  echo 'Full Git history is required for secret scanning.' >&2
  exit 1
fi
mkdir -p reports
docker run --rm --network none -v "$PWD:/repo:ro" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo \
  "$GITLEAKS_IMAGE" git /repo --redact --exit-code 1
docker run --rm --network none -v "$PWD:/src:ro" -w /src \
  -e SEMGREP_USER_DATA_FOLDER=/tmp/semgrep "$SEMGREP_IMAGE" \
  semgrep scan --config /src/.semgrep.yml --metrics off --disable-version-check --error /src/app /src/devops_toolkit
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONUSERBASE=/tmp/python-user \
  -v "$PWD:/src" -w /src "$PYTHON_IMAGE" sh -ec \
  'pip install --user --only-binary=:all: --require-hashes -r requirements-dev.txt
   python -m coverage run -m unittest discover -s tests -v
   python -m coverage xml
   python -m coverage report --fail-under=85'
docker run --rm -v "$PWD:/src:ro" -w /src "$HELM_IMAGE" \
  lint charts/platform --set image.tag="$GIT_SHA"
docker run --rm -v "$PWD:/src:ro" -w /src "$HELM_IMAGE" \
  template platform charts/platform --set image.tag="$GIT_SHA" > reports/rendered.yaml
docker run --rm -v "$PWD:/src:ro" -w /src "$HELM_IMAGE" \
  template platform charts/platform -f charts/platform/values-production.yaml \
  --set image.digest="sha256:$(printf '%064d' 0)" > reports/rendered-production.yaml
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/src" -w /src/infra "$TERRAFORM_IMAGE" fmt -check
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/src" -w /src/infra "$TERRAFORM_IMAGE" init -backend=false
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/src" -w /src/infra "$TERRAFORM_IMAGE" validate
