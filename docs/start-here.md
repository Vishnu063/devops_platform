# Understand the project in ten minutes

## The problem

A deployment can fail because an image is wrong, a required Secret is missing, probes are absent or the cluster lacks room. During an incident, engineers often repeat the same commands to collect evidence.

This project combines a delivery pipeline with deployment checks, incident snapshots and offline comparison to reduce that repeated work.

## The three commands

| Command | Use it when | Result |
| --- | --- | --- |
| `preflight` | Before a deployment or while reviewing configuration | Findings with PASS, FAIL, UNKNOWN or WARN |
| `incident` | Before a release or when an application is unhealthy | A private JSON evidence folder |
| `compare` | After collecting before/after snapshots | Changed images, replicas, restarts and warning events |

Read [the toolkit guide](toolkit.md) for copy-paste commands.

## The application

The small Flask API is the deployment target. It returns its version and exposes health and metrics endpoints. Gunicorn serves it inside a restricted Docker container.

## How a change reaches Kubernetes

1. Git stores the code and reviewed changes.
2. CI runs tests and source checks.
3. Docker builds one image; scanners inspect it.
4. SonarQube and Snyk must pass before publication.
5. GitHub publishes and signs the image digest.
6. A reviewed release file selects the digest.
7. Argo CD applies that configuration after manual sync.
8. Prometheus and Grafana help observe the service.

## Where to look

| Question | Read |
| --- | --- |
| What can I run first? | [Toolkit commands](toolkit.md) |
| How do I install and deploy it? | [Setup](setup.md) |
| Why were these choices made? | [Design decisions](decisions.md) |
| What do I do when it fails? | [Runbook](runbook.md) |
| What should I learn? | [Learning guide](learning.md) |
| What remains unverified? | [Readiness](readiness.md) |

## Current limits

The tools are read-only helpers. They do not fix incidents, guarantee scheduling or approve deployments. The default AWS setup is a single-node lab. Production use requires target-environment validation and configuration.

Tests, builds, scanner engines and live deployment remain pending. Example outputs in the documentation are illustrations, not claimed results.

## Try comparison without Kubernetes

```bash
python -m devops_toolkit compare examples/snapshots/before.json examples/snapshots/after.json
```

These are illustrative files, not real incident evidence. Read the output as observations to investigate, not an automatic root-cause diagnosis. See [the comparison guide](compare.md).
