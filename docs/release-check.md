# Check a release before deployment

`release-check` combines evidence into **BLOCKED**, **NEEDS_REVIEW** or **CHECKS_PASSED**. It is read-only. It does not deploy, repair, modify Git or approve a release.

```bash
devops-toolkit release-check --context YOUR_CONTEXT --namespace platform \
  --deployment YOUR_DEPLOYMENT --service YOUR_SERVICE \
  --file candidate.yaml --policy reports/recovery-policy.local.json \
  --output reports/release-check.json
```

Create `reports/` first. Omit `--file` to inspect an existing live Deployment instead of a proposed change. Use `--service` to identify the intended Service; a same-named Service inside the candidate List takes precedence over its live version. Avoid checking unrelated Services from a multi-application List as if they belonged to this Deployment.

Input is JSON, multi-document Kubernetes YAML, or a trusted local Helm chart. It must contain exactly one matching Deployment and the intended Service; namespace must match. Use `--chart`, `--release`, repeatable `--values` and `--set` instead of `--file` for bounded local `helm template` rendering. Install the optional YAML extra first. See [manifest input](manifest-input.md). Hooks are not executed and server admission is not part of release-check.

## Six practical questions

| Question | Evidence collected | Meaning and limits |
| --- | --- | --- |
| Does the image exist? | Digest format and `docker manifest inspect` | PASS means accessible with local Docker credentials. A failed lookup is UNKNOWN because credentials/network can fail. Node registry identity, CPU architecture and signatures are not verified. |
| Are required Secrets/ConfigMaps available? | Live object and referenced key names via kubectl templates | Checks required env, envFrom, volumes, projected volumes and pull-secret references. Values are excluded from reports; the identity still needs Secret get permission. Same-release proposed configuration is not assumed live. |
| Can the workload fit? | Allocatable minus assigned pod requests on eligible nodes | Conservative one-new-pod CPU/memory estimate, with init/overhead handling. No full-rollout placement, quota, affinity, PVC, topology or pending-reservation simulation. |
| Will its Service select intended pods? | Proposed labels, Service selector and named targetPort declarations | Mismatch blocks. Matching labels do not prove the Service selects only these pods or that the app listens/responds. |
| Could this reduce availability? | Recreate strategy, maxUnavailable rounding, downscale, current availability, selector immutability and readiness configuration | Reports configuration risks and definite selector incompatibility. It does not predict outages or validate application dependencies. |
| What recovery is approved? | Optional policy schema/expiry, context, namespace UID, Deployment UID, candidate hash and opt-in | Summarizes a matching action without running it. Other guards, admission and conditions remain live requirements. A pre-defaulted manifest hash can differ from the server-defaulted template; regenerate from the observed state when appropriate. |

Image inspection requires Docker on PATH and registry access; it does not require building or pulling an image. `--skip-image-check` explicitly skips it and produces a review warning. There is no flag to silently reinterpret missing evidence as a pass.

A policy for a Service is not a rollback policy for a Deployment. The release-check recovery summary currently expects a Deployment image/container/replica policy. Review Service repair separately. Recognized Argo CD/Flux ownership produces a warning to repair Git instead of fighting its controller. Namespace pause/process stop is also reported.

## Read the decision

- **BLOCKED / exit 1:** at least one checked requirement failed, such as a missing required live key or a selector mismatch.
- **NEEDS_REVIEW / exit 2:** evidence is incomplete, a check was skipped, recovery is unapproved, or a risk needs a person to assess it.
- **CHECKS_PASSED / exit 0:** implemented checks passed for this observation. This is not a deployment approval or a promise of availability.
- **Exit 3 with notifications:** checks completed successfully but the configured outcome notification failed; inspect the actual report.

Fixed scope limits are always visible as NOTE/limitations, even when checks pass. Collection is not atomic. Capacity and configuration can change immediately after the report. No scanner, admission, rollout or real traffic test is executed by this command.

Permissions are described in [operations](operations.md). Missing namespace-wide capacity or Secret access can result in incomplete checks; do not grant cluster-admin simply to remove UNKNOWN results. Code and regression cases are included; execution and live validation remain pending.

## Pipeline and investigation integration

[Automatic offline CI](ci-integration.md) reports configuration checks separately from live readiness. [Drift](drift.md) explains desired/live field differences, [server dry-run](dry-run.md) validates an approved repair without saving it, and [workload bundles](bundle.md) collect scoped incident evidence. Mocked regressions and offline CI have passed; live release-check/drift/dry-run/bundle validation remains outside that evidence. See [compatibility](compatibility.md).
