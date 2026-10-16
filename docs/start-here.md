# Start with the engineer's task

New here? Follow [the short offline walkthrough](easy-start.md). Start with `doctor`, explore a fabricated `example`, and open a local HTML `report`. `guide` plans commands interactively without running them.

Export saved evidence with [report/handover](reports.md), or prepare an image-only [GitOps source proposal](gitops-proposals.md) for review.

## Before a deployment

Use [release-check](release-check.md). It checks image access, required live configuration, estimated capacity, Service matching, availability risks and recovery approval. It returns BLOCKED, NEEDS_REVIEW or CHECKS_PASSED with reasons. It does not deploy or guarantee success.

## During an incident

Use `diagnose` to collect symptoms, `incident` to save a private snapshot and [timeline](timeline.md) to correlate snapshots with a repair audit. Comparison and timeline are offline. Observations are evidence, not proof of root cause.

## For one approved automatic correction

Use [policy create](policies.md). You provide the known compatible fix; the generator fills live UIDs/hashes and expiry. Enable execution explicitly only after review. [Repair](automatic-repair.md) covers images/container fields, selectors and upward replica restoration within its limits. GitOps ownership should remain with its controller.

## For a completion message

Set up an approved receiver using [alerts](alerts.md). Messages contain a fixed result record rather than reports, logs or credentials. Notifications are off by default.

## To learn and demonstrate later

Read [the demo guide](demo.md). Four disposable scenarios demonstrate image, selector, replica and readiness-configuration correction when run. No demo is running now. The [learning guide](learning.md) explains the wider delivery pipeline.

## Install and navigate

Follow [README](../README.md) to install the console CLI from source, or use `python -m devops_toolkit` from the repository. No PyPI package is published. Optional YAML/Helm input uses `pip install '.[yaml]'`; base JSON operation stays standard-library-only. The toolkit uses Python 3.12+ standard library; kubectl/Docker requirements depend on the command. The Flask API is a separate delivery target with its own dependencies.

| Need | Guide |
| --- | --- |
| Existing detailed command reference | [Toolkit](toolkit.md) |
| Stop automation and review permissions | [Operations](operations.md) |
| Intended versions versus verified results | [Compatibility](compatibility.md) |
| Install infrastructure or deploy the API later | [Setup](setup.md) |
| Design and production gaps | [Decisions](decisions.md), [readiness](readiness.md) |
| Contribute or report a bug | [Contributing](../CONTRIBUTING.md), [security](../SECURITY.md) |

Source installation, offline commands, regression tests and disposable recovery scenarios now have [execution evidence](compatibility.md). Real alert delivery and production validation remain pending. Code presence is not production validation. No automation is installed or enabled by reading these guides or generating a policy.

## In an existing delivery pipeline

Use [manifest input](manifest-input.md) for existing YAML/JSON or a local chart. The new [automatic CI job](ci-integration.md) adds offline reports to PR Checks without credentials. Trusted connected checks remain opt-in. For investigation, use [drift](drift.md), [server-side repair validation](dry-run.md) and [workload bundles](bundle.md). Automatic CI has run successfully; see [compatibility](compatibility.md) for commit-specific results.
