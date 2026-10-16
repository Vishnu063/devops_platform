# Compatibility and observed validation

The toolkit is development version `0.3.0.dev0`. A passing test or disposable demo is evidence for that environment and commit, not production certification.

## Verified on 2026-10-16

| Component | Observed environment | Result and boundary |
| --- | --- | --- |
| Local runtime | CPython 3.12.14, Linux amd64 | 97 application/toolkit tests passed after the EndpointSlice fix (96 passed before it) |
| Source build/install | Fresh virtual environment, pinned setuptools backend, PyYAML 6.0.3 | Wheel built and installed; console smoke passed from outside the source checkout |
| Installed CLI | version, doctor, noninteractive guide boundary, example, suggest, HTML report, handover | Actual successful offline commands; synthetic incident, no live cluster |
| Automatic CI | GitHub Ubuntu 24.04 runner, source commit `363a50fdd883585e7acd1b98b0613169cae07c7f` | [Toolkit checks passed](https://github.com/Vishnu063/devops_platform/actions/runs/38852783998): installation, console smoke, 89 toolkit tests and isolated Helm/configuration gate |
| Helm configuration gate | CI tool image `alpine/helm@sha256:d899e6316789fec04ee95300a18e454b7942539cbb3d89bde3e0655d6ca2e895` | Offline rendering/check gate passed; Helm semantic version was not logged, so no version range is claimed |
| Local Kubernetes demo environment | Python 3.12.3; kind v0.33.0 built with Go 1.24.13; kubectl and server v1.37.0; Linux amd64 | Exact versions read from the successful replica demo's `results.json`; one environment, not a broader support matrix |
| First live scenario matrix | Same source commit as above | [Images, replicas and configuration passed; selector failed](https://github.com/Vishnu063/devops_platform/actions/runs/38852783905). Clusters were cleaned up. Selector failure occurred while observing the injected fault, before repair |
| EndpointSlice correction | Commit `a217ad5897dec2c5bc942bf3fda9cb2df97c3d8d` | Null endpoint lists now mean no ready endpoints. All 97 local tests, [fresh CI](https://github.com/Vishnu063/devops_platform/actions/runs/38853058232) and [all four live scenarios](https://github.com/Vishnu063/devops_platform/actions/runs/38853058233) passed. Each scenario verified HTTP recovery, one acknowledged repair, repeat-attempt refusal and cluster cleanup |

The demo node image is `kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5`. Exact application-image digest, versions, scenario stages and cleanup state are retained in each run's evidence artifact. GitHub artifacts expire after seven days; job logs/run links remain the primary navigation. Do not infer success from an expired or absent artifact.

[Durable validation summary and exact scenario stages](validation/2026-10-16.json) preserve the observed results after temporary CI artifacts expire. The tested source commit is `a217ad5897dec2c5bc942bf3fda9cb2df97c3d8d`; later documentation/media-only commits do not create a new runtime-support claim.

## Still outside the verified scope

- Production/EKS/AKS/GKE clusters, alternate Kubernetes versions, admission policies, authentication plugins and operating systems.
- Real Slack/Teams/webhook delivery, cloud infrastructure, signed image publication and a production deployment.
- Live drift, server dry-run and scoped bundle behavior beyond the mocked regression cases.
- Load, concurrency, sustained availability, disaster recovery and application/business SLOs.
- Independent engineer usability feedback. Automated checks and the [offline video](walkthrough.md) are not a user study.

Python 3.12+ remains the intended runtime, but only the exact observed versions above have execution evidence. Helm rendering passed in the pinned CI tool image; it is not a claim that arbitrary Helm releases/charts are compatible. No PyPI package or production release was published.
