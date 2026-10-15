# DevOps Platform Toolkit

**Check a Kubernetes release, understand an incident, and recover an explicitly approved failure.**

Use this when you are about to deploy and want one readable answer to: **what is missing, what could reduce availability, and what recovery is actually approved?** During an incident, collect evidence and build a timeline rather than repeating the same investigation commands.

**Status: development version `0.2.0.dev0`.** Features, regression cases and demo workflows are included. Tests, package installation/build, scanners, notification delivery and live recovery have **not been run** for this revision. Nothing is deployed or enabled. This is not a production-validated auto-healer.

## Why a DevOps engineer would use it

| Your question | What the toolkit checks | Important boundary |
| --- | --- | --- |
| Does this image exist? | Digest and registry access | Local registry identity; not a signature or node-pull guarantee |
| Are Secrets and ConfigMaps available? | Required live objects and keys | No values in reports; proposed same-release objects are not assumed present |
| Can a new pod fit? | Estimated CPU/memory headroom | One pod; not full rollout, quotas or scheduler simulation |
| Will the Service select these pods? | Candidate labels, selectors and named ports | No proof of exclusive selection or real traffic |
| Could this reduce availability? | Recreate, maxUnavailable, downscale, readiness and live baseline | Configuration risks, not an outage prediction |
| What recovery is approved? | Policy expiry, scope, UID, candidate hash and opt-in | No policy means no approved direct recovery |

The report says **BLOCKED**, **NEEDS_REVIEW** or **CHECKS_PASSED**, with evidence. Missing access, skipped checks and uncertainty stay visible. Passing implemented checks is not deployment approval.

## Install the CLI when you are ready

From this repository, using Python 3.12 or later:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Then use `devops-toolkit ...`. Installation is supplied as source configuration and remains unverified; no package is published to PyPI. All commands also work from the repository as `python -m devops_toolkit ...`, without installing the CLI package. The toolkit has no third-party Python runtime dependencies. Cluster reads need kubectl; image checks need Docker.

## A practical workflow

### 1. Check a release without deploying it

```bash
mkdir -p reports
devops-toolkit release-check --context YOUR_CONTEXT --namespace platform \
  --deployment YOUR_DEPLOYMENT --service YOUR_SERVICE \
  --file candidate.local.json --output reports/release-check.json
```

Input is a Deployment JSON or Kubernetes List JSON. Omit `--file` to inspect the live Deployment. Supply `--policy` if you have a reviewed recovery approval. Helm/YAML rendering stays in your existing toolchain. [Read the six checks and limits](docs/release-check.md).

### 2. Generate a policy without copying IDs or hashes

Supply a reviewed JSON correction, such as container names mapped to known compatible image digests:

```bash
devops-toolkit policy create --context YOUR_CONTEXT --namespace platform \
  --kind Deployment --name YOUR_DEPLOYMENT --action images \
  --approved approved-images.local.json --output reports/recovery-policy.local.json
```

The generator reads live identities and hashes for you. It requires the workload's existing opt-in and preserves repair guards. It does not invent a fix or enable automation. [Examples for all four actions](docs/policies.md).

### 3. Recover only after explicit enabling

```bash
devops-toolkit watch-recovery --policy reports/recovery-policy.local.json \
  --execute --audit reports/recovery-UNIQUE-ID.jsonl
```

The image monitor waits for persistent failed-rollout evidence, makes one conditional repair and checks readiness. `repair` supports approved container fields, Service selector and upward replica restoration. Preview is the default. Scope, expiry, GitOps/HPA ownership checks, audit and attempt latches apply. Namespace pause and process stop controls are available. [Repair guide](docs/automatic-repair.md) · [Stop and permissions](docs/operations.md).

### 4. Understand what happened

```bash
devops-toolkit incident --context YOUR_CONTEXT --namespace platform --output reports/before
# Collect additional snapshots when appropriate, using new folders.
devops-toolkit timeline reports/before/report.json reports/after/report.json \
  --audit reports/recovery-UNIQUE-ID.jsonl --output reports/timeline.md
```

The timeline shows observed symptoms, differences and scoped repair events. It does not prove root cause. [Timeline guide](docs/timeline.md).

### 5. Receive optional outcome alerts

Add `--notify-config alerts.local.json` to an operational command. Configure Slack, Teams or a generic HTTPS receiver through a secret environment variable. Nothing is sent by default; sensitive reports and target identities are excluded from notifications. [Alert setup and delivery limits](docs/alerts.md).

## See a repair on a disposable local cluster later

The code includes four scenarios:

```bash
devops-toolkit demo --scenario images
devops-toolkit demo --scenario selector
devops-toolkit demo --scenario replicas
devops-toolkit demo --scenario configuration
```

Each creates its own local kind cluster, introduces a known fault, attempts its approved correction, checks HTTP and audit evidence, writes a timeline and removes its cluster. It requires local Docker, kind and kubectl. These commands **create and delete local resources when run**. They are not being run as part of this update.

Or choose **Actions → Local recovery demo → Run workflow** and select one scenario. The workflow is manual only. **All four live scenarios remain unverified.** [Demo guide](docs/demo.md).

## Commands at a glance

| Command | Purpose | Changes cluster state? |
| --- | --- | --- |
| `release-check` | Six checks and one readable decision | No |
| `preflight` | Detailed configuration/reference/capacity checks | No |
| `diagnose` | Workload symptoms and suggested next actions | No |
| `policy create` / `policy check` | Generate private approval / validate offline | No |
| `incident` | Save a private namespace snapshot | No |
| `compare` / `timeline` | Compare/correlate saved evidence offline | No |
| `recover` / `watch-recovery` | One approved image repair | Only with `--execute` |
| `repair` | Approved container, selector or replica correction | Only with `--execute` |
| `demo` | Disposable local recovery scenario | Yes, its newly created local cluster only |

## What it will not automatically fix

Application bugs, missing credentials, arbitrary network failures, storage corruption, node failures and control-plane disasters need an engineer or the owning platform controller. GitOps-managed resources should be repaired through approved Git state; direct repairs refuse recognized Argo CD/Flux ownership. An approved image correction is not a full revision or database rollback.

Read [all Kubernetes problem types](docs/kubernetes-problems.md), [compatibility/evidence](docs/compatibility.md), [contribution guide](CONTRIBUTING.md), [security reporting](SECURITY.md) and [changelog](CHANGELOG.md). The Flask API and infrastructure below remain the separate delivery/learning target.

## Delivery flow

```mermaid
flowchart TD
  A["Manual CI run"] --> B["Tests, secrets, SAST, manifest checks"]
  B --> C["Build once, Trivy, SBOM"]
  C --> D["SonarQube and Snyk"]
  D --> E["Approved publish job"]
  E --> F["GHCR digest, signature and SBOM attestation"]
  F --> G["Reviewed release PR"]
  G --> H["Argo CD manual sync"]
  H --> I["Kubernetes and monitoring"]
```

CI stays manual until initial validation is complete. A check-only run does not publish. A release run requires SonarQube and Snyk to pass before the saved image is published. Missing credentials stop the release.

## Run locally

The dependency lock targets **CPython 3.12 on Linux amd64**. Docker Compose also selects amd64.

```bash
docker compose up --build -d
curl http://127.0.0.1:8080/
docker compose down
```

For a local Python environment:

```bash
python -m venv .venv
source .venv/bin/activate
make install
make run
```

Gunicorn serves the application with one process and four threads per pod. Request metrics are process-local; scale pods rather than increasing worker processes.

| Endpoint | Purpose |
| --- | --- |
| GET / | Service name and source version |
| GET /health/live | Process health |
| GET /health/ready | Service readiness |
| GET /metrics | Request counters and latency histogram |

The service is stateless and has no downstream dependency. Logs omit query strings and use matched routes to avoid logging arbitrary paths. Optional Ingress exposes only the exact root path; health and metrics stay internal.

## Project layout

| Path | Contents |
| --- | --- |
| devops_toolkit/ | Deployment checks, evidence, diagnosis and opt-in approved repairs |
| app/, tests/ | API and regression tests |
| ci/ | Shared checks used by GitHub Actions and Jenkins |
| .github/workflows/ | Check, release and reusable quality jobs |
| charts/platform/ | Helm chart and multi-zone deployment profile |
| gitops/ | Restricted Argo project and release configuration |
| infra/, ansible/ | Optional single-node AWS lab |
| monitoring/ | Scrape configuration, alerts and dashboard |
| docs/ | Setup, decisions, runbook, learning and review notes |

## Release controls

GitHub Actions is the publishing authority. Jenkins runs the same source, image and external quality checks, but does not publish.

Releases use:

- Hash-locked Python dependencies and digest-pinned base/tool images.
- Git-history scanning with Gitleaks and local Semgrep rules.
- Trivy and Snyk gates for high/critical container vulnerabilities.
- SonarQube analysis and a blocking quality gate.
- The same saved image archive across scanning and publication.
- Cosign keyless signing and an SBOM attestation on the registry digest.

Configure the GitHub `production` environment with required reviewers and main-only deployment rules. The workflow declaration alone does not enforce those account settings. Signature verification is a release-review step; cluster admission enforcement is not included.

## Deployment profiles

The default chart runs a small lab. The production profile requires an approved image digest, at least three eligible nodes across two zones, metrics-server and a NetworkPolicy-enforcing CNI. It adds strict placement and autoscaling; it does not provision that infrastructure.

Terraform and Ansible deliberately remain a **single-node lab**. They are not a production cluster or a free-cost guarantee. EC2, storage and public IPv4 may be billed.

Start with [the walkthrough](docs/start-here.md), [toolkit commands](docs/toolkit.md), [setup](docs/setup.md), [design decisions](docs/decisions.md), [runbook](docs/runbook.md), [learning](docs/learning.md), and [review findings](docs/review.md). [Deployment notes](docs/readiness.md) list the evidence still needed before production use.
