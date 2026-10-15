# Deployment readiness

Repository safeguards are implemented. Runtime and environment validation are still pending.

| Area | In the repository | Still required |
| --- | --- | --- |
| Runtime | Flask, Gunicorn, graceful shutdown, restricted container | Execute tests, build, load and shutdown checks |
| Dependencies | Exact versions, wheel hashes, image/action pins | Run vulnerability scans and maintain pins |
| Release | Same image across gates, fail-closed publication, signing and SBOM attestation | Configure tokens and environment reviewers; verify an actual release |
| Kubernetes | Probes, resource limits, PDB, network isolation, HPA and multi-zone profile | Validate chart rendering and behavior on the target cluster |
| GitOps | Restricted project and digest-based promotion | Configure access and prove release/rollback |
| Public access | Optional root-only Ingress and TLS-secret reference | Controller, DNS, certificates, HTTPS policy, rate limits and access controls |
| Infrastructure | Isolated EC2 lab and backend example | Choose/provision HA infrastructure and protect state |
| Monitoring | Request/latency metrics, discovery/down/error/latency alerts, dashboard | Confirm scrape selectors, receivers and measured thresholds |
| Operations | Recovery guidance and incident exercises | Owners, SLOs, capacity, alert delivery and recovery evidence |

## Deployment profile requirements

The production Helm profile requires at least three schedulable Linux amd64 nodes across two zones. It uses strict spreading and requests three to six replicas. Keep spare capacity for a rolling update. Metrics-server and a NetworkPolicy-enforcing CNI are required.

The default AWS node does not meet these requirements. No production cluster is automatically created.

## Remaining release policy work

Configure GitHub branch/environment protection before publishing. The checks remain manual-only. Cluster-side signature/admission enforcement is not included, so an administrator could bypass GitOps and deploy another image. Restrict cluster write access and install an appropriate admission policy before requiring enforcement.

## Validation record

Completed: file-by-file source/configuration review; upstream action/image references resolved; Python wheels downloaded and hashes recorded; Python/plain-YAML/JSON/Bash syntax checked without executing the application.

Not executed: unit/integration tests, coverage measurement, security scanner engines, Docker builds, Helm/Terraform runtime validation, cloud apply or live operational exercises.

Do not label a deployment production-ready until these checks pass in the chosen environment and its operating requirements are documented.

## Toolkit usability revision (unexecuted)

Source adds an installable CLI, policy generation, combined release checks, offline timelines, opt-in alerts, stop controls and four local demo scenarios. Installation/build, unit tests, real notifications, permissions, live Kubernetes compatibility and all scenario runs remain pending. See [compatibility](compatibility.md) and [CHANGELOG](../CHANGELOG.md). This revision did not run tests, demos, scanners, workflows, builds or deployments.

## CI/CD input and investigation revision (unexecuted)

Source adds direct YAML/Helm input, future automatic offline PR checks, an opt-in trusted Jenkins live gate, redacted drift paths, server-side repair dry-run and ownership-scoped bundles. Current publication deliberately uses `[skip ci]`; no tests, builds, CLI commands, pipeline jobs, cluster calls or notifications were executed. Credentials, branch protection and trusted live runner setup are not configured by repository files alone.
