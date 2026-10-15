# Changelog

## Unreleased — 0.3.0.dev0

- Safe multi-document YAML/JSON input and bounded local Helm rendering with optional pinned YAML dependency.
- Automatic offline toolkit/configuration PR/main checks with job summary and narrowly scoped report artifacts.
- Shared Jenkins offline stage and explicit opt-in live release-check gate with private output handling.
- Desired-versus-live drift reports that omit field values.
- Server-side approved-repair dry-run without persisting a latch or patch.
- Ownership-scoped workload bundles with opt-in bounded logs.

This revision is code/documentation only. It is committed with `[skip ci]`; tests, package install/build, scanners, chart rendering, workflow jobs, cluster queries/patches, notifications and deployments remain unrun. Live CI setup and repository protection are operator responsibilities.

## Previous development snapshot — 0.2.0.dev0

- Installable `devops-toolkit` console command with no third-party Python runtime dependencies.
- Policy creation from live UIDs/spec hashes and an explicit approved correction; offline policy validation.
- Combined release checks for image access, required configuration, estimated one-pod capacity, Service matching, availability risks and recovery authorization.
- Offline incident timeline correlating snapshots with scoped repair audit events.
- Optional Slack, Teams and generic HTTPS outcome notifications; no notifications enabled by default.
- Namespace repair pause and process-level emergency stop, checked before direct mutations.
- Disposable demo scenarios for image, Service selector, replica-count and readiness-configuration repair.
- Contribution guidance, issue/PR templates, permissions examples and compatibility documentation.

This entry describes code and documentation added. Tests, package installation/build, scanner runs, demos, notification delivery and live deployment/recovery remain unexecuted for this revision. No package has been published and no release tag has been created.
