# Deployment safeguards and outstanding work

## Implemented, not yet verified

- Helm accepts either a full Git commit SHA tag or a valid sha256 digest. Digest wins when both are supplied.
- A startup probe allows up to 30 seconds before liveness/readiness checks begin.
- Replica placement prefers different hosts when capacity exists. It remains schedulable on one node, so this is not an HA guarantee.
- NetworkPolicy denies outbound traffic from the API and limits inbound traffic to labeled Prometheus pods in the monitoring namespace.
- Ingress-controller access is disabled by default; enable it only after matching its namespace and pod labels.
- No tests, scans, render checks or deployment exercises were run for these changes.

## Image identity

After building and pushing, obtain the image digest from the registry, inspect that it belongs to the intended CI build, and record it in gitops/release.yaml:

```yaml
image:
  repository: ghcr.io/vishnu063/devops_platform
  tag: ""
  digest: sha256:REPLACE_WITH_THE_ACTUAL_64_CHARACTER_DIGEST
```

The example above is intentionally invalid until replaced. A digest identifies immutable content, but does not establish who built it or whether it passed security checks. Review the build and scan evidence separately. Signing and admission enforcement are not implemented.

## Network boundaries

The CNI must enforce Kubernetes NetworkPolicy. The policy permits only TCP 8080 from Prometheus pods labeled app.kubernetes.io/name=prometheus in namespace monitoring. Adjust selectors to your actual stack. It does not distinguish HTTP paths; monitoring pods can access all API routes.

The service performs no outbound calls, so it needs no DNS exception. Image pulls happen through the node and are not API-container egress. If dependencies are added, add specific egress rules as part of that change.

Port forwarding remains the operator access method. No public Ingress, hostname or TLS certificate is supplied. NetworkPolicy is not a substitute for authentication or TLS.

## Before calling this production-ready

| Requirement | Outstanding evidence or implementation |
| --- | --- |
| Code and manifests | Execute tests, coverage, Helm rendering and Terraform validation |
| Supply chain | Verify tool/image references, pin digests and action SHAs, scan, sign and enforce policy |
| Release gates | Enable automatic checks and branch protection; require external gate results for the release SHA |
| Infrastructure | Choose HA topology, capacity, state backend, recovery strategy and cost controls |
| Public access | Configure a real domain, TLS, ingress, access control and rate limits if needed |
| Reliability | Exercise rollouts, rollback, node loss, alert delivery and load behavior |
| Operations | Define owners, SLOs, escalation and measured recovery objectives |

This is a hardening increment for a portfolio lab. Completing source files does not establish operational production readiness.
