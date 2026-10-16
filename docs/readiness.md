# Deployment readiness

Repository safeguards are implemented. Runtime and environment validation are still pending.

| Area | In the repository | Still required |
| --- | --- | --- |
| Runtime | Flask, Gunicorn, graceful shutdown, restricted container | Application tests passed; image build, load and shutdown checks remain |
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

Configure GitHub branch/environment protection before publishing. Offline toolkit CI is automatic; image/security/publication and production deployment approvals remain separate and manual. Cluster-side signature/admission enforcement is not included, so an administrator could bypass GitOps and deploy another image. Restrict cluster write access and install an appropriate admission policy before requiring enforcement.

## Validation record

See [compatibility](compatibility.md) for commit-specific test, installation, CI and disposable demo outcomes. Those checks do not prove production readiness. Earlier code-only additions intentionally deferred execution; the current record supersedes those historical unexecuted-status notes.

Remaining work includes production-like load/shutdown behavior, live command compatibility beyond the demos, security/release pipeline execution, cloud/GitOps integration, real alert delivery, operator controls and independent usability feedback. No production deployment or infrastructure provisioning was performed.

## Track the remaining checks

Use the [validation checklist](validation-checklist.md) for branch protection, cloud-cluster acceptance, real notification delivery, the release path and independent feedback. Mark an item complete only when its execution evidence has been recorded.
