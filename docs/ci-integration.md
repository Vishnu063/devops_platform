# Use release checks in CI/CD

There are two separate jobs: an **automatic offline configuration check** for PRs and a **trusted live check** only when an operator configures cluster access. Neither job deploys or repairs anything. Existing publishing/security-gate workflows stay manual.

## Automatic GitHub pull-request checks

`.github/workflows/toolkit-checks.yml` is configured for relevant pull requests, main-branch pushes and manual dispatch. It runs on an ephemeral GitHub Ubuntu runner with `contents: read` and no configured repository/cluster secrets. It does not use `pull_request_target`, a self-hosted runner, write tokens or a production environment.

The job:

1. Installs the toolkit from the checked-out source with the optional YAML dependency.
2. Runs the focused offline toolkit regression suite. No actual cluster or webhook is part of those mocks.
3. Renders this repository's chart with a pinned Helm container, a read-only source mount and no network inside the rendering container.
4. Checks the rendered Deployment/Service configuration using `manifest-check`.
5. Adds a concise result to the job summary and attaches only the configuration JSON/summary artifacts.

Open **PR → Checks → Offline toolkit and manifest checks → Summary** to read the result or download `toolkit-configuration-report`. This attaches evidence to the PR check; it does not post a bot comment or require issue/comment write access. Repository settings and fork-contributor approvals can still control whether GitHub starts a run.

The rendering values use an explicitly fake digest under `example.invalid`. This is a **configuration-only fixture**, never a built image or deployment candidate. The report labels live readiness `NOT_ASSESSED_OFFLINE`. It cannot verify a live Secret, registry access, capacity, admission or traffic. Raw rendered YAML is temporary and is not uploaded.

The repository job uses `--warnings-as-errors`: definite configuration errors, configuration warnings and test/tool failures fail the check. The standalone CLI can omit that flag when a team wants to review warnings without failing its offline gate. Passing this job is not a production release approval. Add the check to branch protection yourself after verifying it; workflow code alone cannot require reviewers or checks in repository settings.

**Execution status:** automatic offline CI has now run successfully, including source installation and installed-console smoke checks. See [the evidence table](compatibility.md) for commit-specific runs. Earlier code-only additions deliberately used `[skip ci]`; skipped commits are not passing evidence.

## Reuse the commands in another pipeline

Install Python 3.12+ and the optional YAML extra, then use either a manifest file:

```bash
devops-toolkit manifest-check --file k8s/release.yaml --namespace platform \
  --output reports/configuration.json
```

or a trusted local chart:

```bash
devops-toolkit manifest-check --chart ./charts/my-app --release my-app \
  --namespace platform --values ./values/staging.yaml \
  --set image.digest=sha256:REPLACE_WITH_DIGEST --output reports/configuration.json
```

Use a new output path and an existing private parent directory. Protect reports according to their contents. Do not automatically upload bundles, kubeconfig, approval policies, raw rendered YAML or connected-cluster reports to public artifacts.

For this repository, `ci/offline-checks.sh` provides the shared test/render/check script used by GitHub Actions and Jenkins. It needs Docker plus a Python interpreter with YAML support; set `TOOLKIT_PYTHON` if using a virtual environment. A clean CI workspace is required so previous evidence is not overwritten.

## Jenkins integration

The existing `Jenkinsfile` remains trusted-main-only. A new Toolkit configuration checks stage prepares a virtual environment and calls the same offline script. Other source, image and external gates remain in place. A `[skip ci]` marker skips those check/build stages after checkout, when that marker is deliberately used. An externally configured Jenkins SCM trigger can still start checkout/cleanup; this repository cannot disable an administrator-owned job trigger. Jenkins job/SCM trust rules still need administrator configuration; a repository script cannot protect credentials from an attacker who controls its Jenkinsfile.

An optional **RUN_LIVE_RELEASE_CHECK** parameter defaults to false. Enabling it requires an administrator to configure the `toolkit-kubeconfig` file credential and the following trusted job variables:

| Variable | Purpose |
| --- | --- |
| `TOOLKIT_CONTEXT` | Explicit context from the approved kubeconfig |
| `TOOLKIT_NAMESPACE` | Target namespace |
| `TOOLKIT_DEPLOYMENT` / `TOOLKIT_SERVICE` | Intended workload and Service |
| `TOOLKIT_CANDIDATE` | Reviewed real candidate YAML/JSON; not the offline fixture |
| `TOOLKIT_PRIVATE_REPORT` | New absolute output path outside the CI workspace, in an existing owner-only directory |
| `TOOLKIT_POLICY` | Optional matching, unexpired Deployment repair approval |

`ci/live-release-check.sh` suppresses detailed stdout, writes the report only to that private destination and prints a generic decision. It refuses a report path inside the workspace or a directory accessible to other users. Do not archive that private destination. With no matching recovery approval, the report can require review; the script does not invent authorization or convert UNKNOWN into success.

Jenkins must have Python 3.12+, Docker and, for the live job, kubectl/registry access and an approved kubeconfig. Live checks return `0` for implemented checks passed, `1` for blocked and `2` for needs-review/incomplete. Nonzero stops the gate. No `--execute`, apply, delete, automatic repair or production deployment is part of either script.

Use a dedicated trusted runner/identity, least privilege and reviewed source. Never bind cluster credentials to untrusted PR code. No live Jenkins variables, credential, schedule or job were configured during this update.

## What CD still needs

The existing signed-image publication and reviewed GitOps release flow remain separate. This addition produces pre-deployment evidence; it does not create a new production deployer, automatically change release digests or bypass SonarQube/security/approval gates. [Release checks](release-check.md), [stop controls/permissions](operations.md) and [validation status](compatibility.md) explain the remaining boundaries.
