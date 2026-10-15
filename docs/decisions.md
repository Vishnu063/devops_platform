# Design decisions

- The API is intentionally small and stateless. This keeps the work focused on delivery, deployment and troubleshooting.
- Python standard library avoids runtime package dependencies; container OS vulnerabilities still need scanning.
- Commit-SHA tags connect a deployment to source. Registry tags are technically mutable; the chart also accepts digests to identify exact image content.
- maxUnavailable=0 and readiness checks reduce rollout disruption, but require spare capacity. PDB protects voluntary eviction only, and cannot prevent a node outage.
- Non-root UID, dropped capabilities, read-only root filesystem and disabled service-account token reduce privileges.
- GitOps separates image publication from release approval. Manual Argo sync provides an explicit deployment step.
- SonarQube is code quality and coverage, Semgrep is a small reviewed SAST rule set, Gitleaks is secret detection, Trivy/Snyk inspect image vulnerabilities. The included Semgrep rule is deliberately narrow, not a complete application security policy.
- No application credentials are required. External scanner tokens stay in CI credential stores.
- Terraform apply is a manual step so infrastructure changes and costs can be reviewed first.
- Single-node k3s is a learning deployment; EKS, multi-zone availability, autoscaling, identity federation, TLS ingress, centralized logging, image signatures and remote state require additional implementation.
