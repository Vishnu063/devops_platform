# Contributing

Start with an issue describing the engineer's problem, minimal sanitized inputs and desired outcome. Keep changes focused. Prefer extending the existing commands to adding another unrelated service.

## Local development

Use Python 3.12 or later. Base JSON operation uses the standard library. YAML and local Helm rendering require the optional pinned PyYAML extra. The Flask delivery target has its own requirements files. Source installation and the regression suites have been executed; see [compatibility](docs/compatibility.md) for exact results and limits.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[yaml]'
python -m unittest discover -s tests -p 'test_product.py' -v
```

Run other relevant toolkit cases and, for application changes, the existing required dependencies and CI checks. Report the exact commands and results. Never claim an unexecuted suite passed. Live drills must target disposable clusters, not production.

## Design expectations

- Default to read-only inspection and preview. Approved fixes must be explicit; do not infer secrets, privileges, desired replicas or a safe rollback image.
- Cluster mutations need exact scope, ownership checks, expiring authorization, a conditional update, durable intent, a persistent attempt latch and bounded verification.
- Stop on unknown outcomes; do not add repeated delete/restart/patch loops or automatic latch clearing.
- Keep namespace pause and process stop controls effective. Document cross-resource races rather than promising atomicity that Kubernetes cannot provide.
- Keep credentials, raw event messages, arbitrary policy fields and logs out of shared reports and alerts.
- Include useful mocked regression cases for refusal and uncertain outcomes, not just happy paths. Include a disposable drill when adding a new repair type.
- Update CLI help, README examples, compatibility notes and CHANGELOG when behavior changes.

## Opening a pull request

Describe the problem and final behavior, with a short example. Include validation actually performed and any limits. Keep secrets and generated reports out of Git. Do not run real notifications or deploy to another user's cluster to reproduce a bug.

Use the issue and pull-request templates. Security findings should follow [SECURITY.md](SECURITY.md), not a public issue containing sensitive data.

## Project status

This is an unvalidated development version. No release tag, package registry publication, successful live-drill result or production support promise is implied. Dependency, integration and Kubernetes compatibility still need execution evidence.

## Pipeline and manifest-input changes

The automatic offline toolkit workflow runs on future matching PR/main events without credentials and checks rendered configuration only. Keep live cluster identity/credentials out of untrusted PR jobs and raw manifests/bundles out of public artifacts. Add mocked cases to `tests/test_ci_tools.py` for parser, drift, dry-run and bundle changes. Use `[skip ci]` only when explicitly deferring execution; a skipped check is not passing evidence. Current execution evidence is recorded in [compatibility](docs/compatibility.md).
