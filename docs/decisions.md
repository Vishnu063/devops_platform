# Design decisions

## Runtime

Flask runs under Gunicorn rather than a development HTTP server. Each pod has one process and four threads. This keeps Prometheus counters consistent within a pod; horizontal scaling happens through Kubernetes. Worker timeouts, bounded request headers and graceful termination are configured explicitly.

The API has no database or downstream dependency. Readiness therefore checks the service itself. Logs use route templates and omit query strings; metric labels are bounded. Gunicorn's control socket is disabled because the container root filesystem is read-only.

## Supply chain

Runtime and development dependencies are pinned with hashes for CPython 3.12 Linux amd64. Base and scanner images use registry digests. Actions use resolved commit SHAs. Pins still require maintenance; they do not guarantee freedom from vulnerabilities.

Source, Helm and Terraform checks are shared by GitHub Actions and Jenkins. Local Semgrep rules cover a few specific risks, not all application security problems. Gitleaks scans full Git history. Trivy and Snyk block high/critical findings without silently ignoring unfixed vulnerabilities.

The image is built once and saved as an archive. Its checksum and image ID are retained across jobs. SonarQube analyzes the same source SHA, Snyk scans that archive, and the publisher loads that archive. Signing and SBOM attestation happen on the final registry digest. Failed signing leaves a potentially pushed but unapproved image; release review must verify success.

## Release and deployment

Only the GitHub release workflow publishes. The production environment requires external GitHub reviewer/branch configuration. Argo CD uses a restricted AppProject, a reviewed digest and manual sync. Signature admission enforcement is not yet installed; verification is required during release review.

The default deployment remains usable on a lab node. The stricter profile requires three nodes and two zones, digest-based images, HPA and a higher disruption budget. Strict spreading may leave pods Pending if topology or capacity is insufficient. HPA does not create nodes.

NetworkPolicy isolates the API; it needs no egress. Optional ingress requires an existing controller and TLS secret. Authentication, rate limits and TLS redirect settings depend on that controller.

## Infrastructure and operations

Terraform and Ansible cover the single-node AWS lab only. This is intentionally separate from production cluster provisioning. Provider initialization, state backend creation, HA cluster design, load testing, backup/restore and alert delivery require environment-specific work.

The service is stateless, so recovery means redeploying an approved image. Git, registry data, infrastructure state, cluster configuration and monitoring credentials still need ownership and recovery arrangements.
