# DevOps Platform Toolkit

Check a Kubernetes release before deploying it, collect evidence when something breaks, and preview a supported repair before running it.

The toolkit brings the usual registry, workload, Service and configuration checks into one CLI report. It also keeps snapshots and repair records so an engineer taking over an incident can see what changed.

This is a development project. Local tests, installed CLI checks and four disposable Kubernetes recovery demos have passed. Cloud deployments, real alert delivery and the full signed-image release path still need validation. [See the recorded results](docs/compatibility.md).

## Try it without a cluster

Requires Git and Python 3.12 or later:

```bash
git clone https://github.com/Vishnu063/devops_platform.git
cd devops_platform
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[yaml]'
devops-toolkit doctor
mkdir -m 700 private-reports
devops-toolkit example --scenario crash --output private-reports/example.json
devops-toolkit report private-reports/example.json --output private-reports/example.html
```

Open `private-reports/example.html` in your browser. The incident is synthetic; these commands do not contact a cluster. Run `devops-toolkit guide` for help choosing your next command.

[Short walkthrough](docs/easy-start.md) · [CLI demonstration](docs/walkthrough.md) · [Command reference](docs/toolkit.md)

## What it helps with

| Task | What you get |
| --- | --- |
| Review a release | Image availability, required Secrets/ConfigMaps, estimated pod capacity, Service matching and availability checks |
| Investigate an incident | Scoped workload evidence, possible causes and suggested next checks |
| Compare changes | Saved snapshots, desired-versus-live field differences and an incident timeline |
| Prepare a repair | A preview tied to an explicitly approved target and correction |
| Check recovery | Bounded readiness checks and an audit record of the attempted repair |
| Share a handover | A local HTML/Markdown report or a draft for your ticket |

Reports distinguish `BLOCKED`, `NEEDS_REVIEW` and `CHECKS_PASSED`. Missing access and incomplete evidence stay visible. A passing check is not deployment approval, and Kubernetes readiness is not proof that users can reach the application.

## Check a real release

Use an explicitly selected context and a private report directory. Replace the sample names with your own workload and reviewed manifest:

```bash
devops-toolkit release-check --context YOUR_CONTEXT --namespace YOUR_NAMESPACE \
  --deployment YOUR_DEPLOYMENT --service YOUR_SERVICE \
  --file k8s/release.yaml --format text --output private-reports/release-check.json
```

This reads the target; it does not deploy or repair it. Registry checks need Docker, cluster reads need kubectl, and chart input needs Helm. The capacity estimate covers one pod, not a complete scheduler or rollout simulation.

[Release checks](docs/release-check.md) · [YAML and Helm input](docs/manifest-input.md) · [CI integration](docs/ci-integration.md)

## Troubleshoot and recover

Start with investigation guidance:

```bash
devops-toolkit suggest --issue CrashLoopBackOff
devops-toolkit suggest --issue stuck
```

For connected-cluster evidence, use `diagnose`, `incident` or `bundle`. Logs are off by default for bundles. Keep connected reports private.

Direct recovery supports approved image corrections, selected container configuration, Service selectors and upward replica restoration. Preview is the default. Execution requires explicit enabling, resource opt-in and an unexpired policy tied to the target state. Recognized Argo CD/Flux ownership blocks direct repair; make the correction in Git instead.

Use the [policy guide](docs/policies.md) and [repair guide](docs/automatic-repair.md) before enabling execution. If an attempt has an uncertain outcome, inspect the live target and audit before trying again. Image restoration is not a database or full application rollback.

[Stop controls and permissions](docs/operations.md) · [Incident timelines](docs/timeline.md) · [Outcome alerts](docs/alerts.md)

## Watch a recovery demo

The four scenarios introduce a known fault in a new local kind cluster, attempt the approved repair, check HTTP recovery and remove that cluster:

```bash
devops-toolkit demo --scenario images
devops-toolkit demo --scenario selector
devops-toolkit demo --scenario replicas
devops-toolkit demo --scenario configuration
```

Requires Docker, kind and kubectl. These commands create and delete disposable local resources. You can also select a scenario under **Actions → Local recovery demo → Run workflow**.

[Demo setup](docs/demo.md) · [Results, including the selector fix](docs/compatibility.md)

## How the delivery project fits in

The repository also contains a small Flask service for practicing delivery. GitHub Actions runs the publication pipeline; Jenkins shares the checks but does not publish. The configured release path includes tests, Gitleaks, Semgrep, Trivy, SonarQube, Snyk, an SBOM and Cosign signing, followed by a reviewed GitOps change and manual Argo CD sync.

Offline toolkit checks run automatically on every pull request and main push. Image publication and deployment remain manual while the release path is being validated. Repository and environment protection must be configured in GitHub settings; workflow files cannot enforce those settings on their own.

For the sample service:

```bash
docker compose up --build -d
curl http://127.0.0.1:8080/
docker compose down
```

The dependency lock and Compose target Linux amd64 with Python 3.12. The service exposes `/`, `/health/live`, `/health/ready` and `/metrics`.

## Find your way around

| Directory | Contents |
| --- | --- |
| `devops_toolkit/` | Checks, reports, incident evidence and approved repairs |
| `app/`, `tests/` | Sample service and regression tests |
| `ci/`, `.github/workflows/` | Shared checks and GitHub Actions workflows |
| `charts/`, `gitops/` | Helm chart and Argo CD release configuration |
| `infra/`, `ansible/` | Optional single-node AWS lab |
| `monitoring/` | Metrics configuration, alert rules and dashboard |
| `docs/` | Setup, design decisions, runbooks and validation records |

The AWS lab is not a highly available production cluster. The production chart profile needs separate infrastructure across multiple zones. Creating cloud resources may incur charges.

## Remaining work

- Configure and verify main-branch and production-environment protection.
- Validate release checks and GitOps on an authorized cloud test cluster.
- Confirm delivery to an approved real alert receiver.
- Run the security, publication, signature verification and deployment path end to end.
- Have another engineer try the setup and incident workflow.

[Validation checklist](docs/validation-checklist.md) · [Deployment readiness](docs/readiness.md) · [Design decisions](docs/decisions.md)

Contributions should describe a reproducible problem and include the checks actually run. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
