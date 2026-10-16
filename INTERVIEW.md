# DevOps Platform Toolkit: reviewer guide

A Kubernetes release-check and incident-evidence CLI with scoped recovery policies and offline reports.

## Start the review

Demonstrate the offline report, explain one release check, and trace the approval boundary before discussing recovery.

| Source | Review focus |\n| --- | --- |\n| [Dockerfile](Dockerfile) | Build context, runtime configuration, ports, and persistence |\n| [Jenkinsfile](Jenkinsfile) | Triggers, credentials, failure handling, and deploy conditions |\n| [compose.yml](compose.yml) | Build context, runtime configuration, ports, and persistence |\n| [pyproject.toml](pyproject.toml) | Implementation, assumptions, and operational boundaries |\n| [.github/workflows/ci.yml](.github/workflows/ci.yml) | Triggers, credentials, failure handling, and deploy conditions |\n| [.github/workflows/docs.yml](.github/workflows/docs.yml) | Triggers, credentials, failure handling, and deploy conditions |

## First demonstration

From a checked-out repository, start with:

```bash
python3 -m devops_toolkit doctor
```

Doctor checks prerequisites only. Continue with docs/easy-start.md for a private offline example report.

## A useful interview walkthrough

1. State the problem and the specific part you implemented or changed.
2. Open the source above and follow one request, release, or failure from start to finish.
3. Show a reproducible result, including an actual failure and the observation that confirms recovery.
4. Explain one tradeoff and one limitation. Distinguish a local test from a live deployment.

## Evidence and limits

This guide is based on the default-branch source inspected on 16 October 2026. It is a source review, not a fresh deployment or a certification of every feature. Existing CI runs and tests should be checked at the commit being demonstrated. Do not present screenshots, inherited code, planned features, or old README statements as proof of a current deployment.
