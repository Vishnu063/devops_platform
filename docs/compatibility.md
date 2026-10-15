# Compatibility and validation status

| Component | Intended interface | Execution evidence for this revision |
| --- | --- | --- |
| Toolkit Python runtime | Python 3.12+ standard library for base JSON mode; optional PyYAML 6.0.3 for YAML | Syntax parsed only; installation and CLI behavior unexecuted |
| Console installation | Local `pip install .` using pinned setuptools build backend | Build/install not run; not published to PyPI |
| Kubernetes reads/patches | apps/v1 Deployment, core/v1 Service/Namespace, autoscaling HPA, discovery.k8s.io EndpointSlice | No live compatibility matrix verified |
| Local demos | Linux amd64 / amd64 Docker Desktop, kind v0.33.0, pinned Kubernetes v1.37.0 node and Python image | Four scenario implementations supplied; no demos run |
| Slack / Teams / generic webhooks | HTTPS JSON POST; text / Adaptive Card / fixed outcome record | No real receiver or delivery tested |
| Offline timeline | Incident schema 1 and scoped JSONL repair audits | Syntax parsed; regression cases supplied, not run |
| AWS / EKS / AKS / GKE | No provider-specific repair implementation | Not verified or certified |
| Argo CD self-heal overlay | Existing optional overlay; direct repair refuses recognized tracking | Not applied or validated |

A Kubernetes version in an API example or demo pin is not a supported-version claim. kubectl/server version skew, admission policies, distribution behavior and authentication plugins need environment validation. The capacity estimate intentionally reports UNKNOWN for some newer resource patterns instead of pretending to simulate scheduling.

The source version is `0.3.0.dev0`. No release tag or published artifact is created by this change. When a real run is performed later, record commit SHA, exact tool versions, environment and observed result; update this table from that evidence. Keep unsuccessful runs visible rather than replacing them with an invented green badge.

## CI usability revision

YAML/JSON parsing, trusted local Helm rendering, offline manifest checks, field-path drift, server repair dry-run and scoped bundles are implemented with mocked cases. Python/YAML/JSON/TOML and shell syntax are the only static checks performed. No package build/install, tests, Helm command, Docker command, registry call, cluster API request, notification or deployment has been run. The new automatic workflow is configured for future events; this update uses a skip marker and has no passing CI evidence. Jenkins credential/job setup remains external.
