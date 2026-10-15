# Repository review

Review date: 2026-10-15. Scope: every file in the repository, including delivery scripts and documentation. This is a source/configuration review, not a passing security-scanner report.

## Findings addressed

| Finding | Change |
| --- | --- |
| Development HTTP server used as deployment runtime | Flask under Gunicorn with request limits and graceful shutdown |
| Release could publish without external quality gates | SonarQube and Snyk now block the release publisher |
| Quality checks rebuilt a different image | Saved image archive, checksum and image ID carried between jobs |
| Jenkins and Actions had different checks | Shared source, image and external-gate scripts |
| Mutable base images, tools and actions | Resolved image digests and action commit pins |
| Coverage paths changed between Docker jobs | Relative-path coverage configuration for SonarQube |
| Runtime dependencies lacked a lock | Exact wheel versions and SHA-256 hashes for Linux amd64 Python 3.12 |
| Sonar scanner could lack workspace permissions | Run with workspace owner and a writable temporary cache |
| Read-only container could break Gunicorn runtime files | Memory-backed /tmp and disabled control socket |
| Registry image had no release identity verification | Keyless signature, SBOM attestation and verification guidance |
| Argo used unrestricted default project | Namespace-limited project with an explicit resource allowlist |
| Single-node placement was described alongside production controls | Separate multi-node/multi-zone profile with digest requirement |
| Missing discovery could evade target-down alert | Missing-target alert alongside down/error/latency rules |
| Installer source was mutable | Pinned installer source/hash and checksum-verified k3s binary |

## File inventory

### Application and container

| File | Review outcome |
| --- | --- |
| `.coveragerc` | Added; relative paths and coverage threshold |
| `app/__init__.py` | Reviewed; retained |
| `app/server.py` | Reviewed; updated |
| `tests/test_server.py` | Reviewed; updated |
| `gunicorn.conf.py` | Added |
| `requirements.txt` | Added |
| `requirements-dev.txt` | Reviewed; updated |
| `Dockerfile` | Reviewed; updated |
| `.dockerignore` | Reviewed; updated |
| `compose.yml` | Reviewed; updated |
| `Makefile` | Reviewed; updated |

### Delivery and security

| File | Review outcome |
| --- | --- |
| `.github/workflows/ci.yml` | Reviewed; updated |
| `.github/workflows/quality.yml` | Reviewed; updated |
| `Jenkinsfile` | Reviewed; updated |
| `ci/check-source.sh` | Added |
| `ci/build-image.sh` | Added |
| `ci/external-gates.sh` | Added |
| `ci/tool-images.env` | Added |
| `.semgrep.yml` | Reviewed; updated |
| `sonar-project.properties` | Reviewed; retained |
| `.github/dependabot.yml` | Added |
| `.gitignore` | Reviewed; updated |

### Kubernetes and GitOps

| File | Review outcome |
| --- | --- |
| `charts/platform/Chart.yaml` | Reviewed; updated |
| `charts/platform/templates/_helpers.tpl` | Reviewed; updated |
| `charts/platform/templates/networkpolicy.yaml` | Reviewed; updated |
| `charts/platform/templates/workload.yaml` | Reviewed; updated |
| `charts/platform/values.yaml` | Reviewed; updated |
| `gitops/application.yaml` | Reviewed; updated |
| `gitops/release.yaml` | Reviewed; updated |
| `charts/platform/values-production.yaml` | Added |
| `charts/platform/templates/ingress.yaml` | Added |
| `charts/platform/templates/hpa.yaml` | Added |
| `gitops/project.yaml` | Added |
| `gitops/namespace.yaml` | Added |
| `gitops/application-production.yaml` | Added |
| `charts/platform/values.schema.json` | Added |

### Infrastructure

| File | Review outcome |
| --- | --- |
| `infra/main.tf` | Reviewed; updated |
| `infra/terraform.tfvars.example` | Reviewed; retained |
| `infra/backend.tf.example` | Added |
| `ansible/k3s.yml` | Reviewed; updated |
| `ansible/inventory.example` | Reviewed; retained |

### Observability

| File | Review outcome |
| --- | --- |
| `monitoring/service-monitor.yaml` | Reviewed; updated |
| `monitoring/grafana-dashboard.json` | Reviewed; updated |

### Documentation

| File | Review outcome |
| --- | --- |
| `README.md` | Reviewed; updated |
| `docs/decisions.md` | Reviewed; updated |
| `docs/learning.md` | Reviewed; updated |
| `docs/readiness.md` | Reviewed; updated |
| `docs/runbook.md` | Reviewed; updated |
| `docs/setup.md` | Reviewed; updated |

This report is also part of the documentation set. Source review does not prove runtime correctness. See readiness.md for pending execution and environment requirements.

Static syntax review completed: four Python files parsed, fifteen plain YAML files loaded, two JSON files parsed and three Bash scripts passed bash -n. Helm templates, Terraform and pipeline runtime behavior still require their tools to run. No application test suite or security engine was executed.
