# Diagnose and recover a failed deployment

## What this adds

`diagnose` reads Kubernetes status and gives next actions. `recover` can automatically restore approved container image digests for one opted-in Deployment after Kubernetes reports `ProgressDeadlineExceeded`. It is a one-shot command. `watch-recovery` adds a bounded monitoring loop that can trigger that recovery automatically after a persistent failed-rollout signal; no controller, service or scheduled job is installed by this repository.

This is image-only recovery, not a full revision rollback. It cannot restore changed environment variables, init containers, volumes, configuration objects or database schemas. Only approve a replacement image compatible with the current configuration and data. No application-level health check or image-signature verification is performed by this command; approve trusted images from the release process.

## Diagnose first

```bash
python -m devops_toolkit diagnose --context YOUR_CONTEXT --namespace platform
```

Add `--include-nodes` for cluster-wide node conditions, or `--output reports/diagnosis.json` for a new private report (create the parent directory first). Reports omit raw event messages, logs and Secret values. They identify symptoms rather than proving a cause.

Exit codes: `0` no findings in captured data, `1` findings, `2` unavailable data or output failure. No findings is not a health guarantee. See [all problem types and countermeasures](kubernetes-problems.md).

## Prepare an approved recovery policy

Use a dedicated non-GitOps lab Deployment for initial validation. The platform application in this repository is Argo CD managed; repair its Git release instead. Ownership detection is best effort: custom GitOps tracking may not be detected. Never opt a controller-managed workload into direct repair.

A workload owner must first explicitly set this Deployment metadata annotation in its approved manifest:

```yaml
metadata:
  annotations:
    devops-platform.io/allow-image-recovery: "true"
```

Copy [the policy template](../examples/recovery-policy.json) to a private local file outside version control. Replace every placeholder:

- `context`: exact kubeconfig context used by this command.
- `namespace` / `deployment`: the one permitted target.
- `namespace_uid` / `deployment_uid`: live identities from `kubectl get ... -o jsonpath='{.metadata.uid}'`. A recreated object requires a new policy.
- `failed_template_sha256`: hash of the exact failed pod template. A different release requires a new policy.
- `approved_images`: every regular container name mapped to its approved compatible image digest. Init containers are not modified.
- `expires_at`: short-lived UTC ISO timestamp, for example a reviewed one-hour repair window. The placeholder deliberately fails validation.

Calculate the template hash without saving the Deployment JSON (which can contain literal environment values). Replace context, namespace and name before running:

```bash
set -o pipefail
kubectl --context YOUR_CONTEXT --namespace platform get deployment YOUR_DEPLOYMENT -o json \
  | python -c 'import json,sys; from devops_toolkit.recovery import fingerprint; print(fingerprint(json.load(sys.stdin)["spec"]["template"]))'
```

Protect the policy file and kubeconfig. Changing an approval file changes the permitted action; only trusted operators should write it. No policy is active out of the box.

## Preview, then enable unattended execution

```bash
python -m devops_toolkit recover --policy /secure/recovery-policy.json
```

Preview reads the cluster and prints the proposed image changes without writing. All eligibility rules also apply to preview. Once the policy and workload have been approved, an operator or trusted scheduler can run:

```bash
python -m devops_toolkit recover --policy /secure/recovery-policy.json \
  --execute --audit /secure/reports/recovery-UNIQUE-RUN-ID.jsonl
```

The audit parent must already exist. Use a unique filename each time; existing files are refused. `--execute` uses the policy as authorization without an interactive prompt. The `recover` command does not loop. Use the built-in `watch-recovery` monitor described below to wait for a failed rollout; there is no installed background service. Scheduler setup, credentials and alert routing remain deployment responsibilities. Treat exit `1` or `2` as requiring an operator alert.

## Limits that prevent repeated or conflicting repairs

1. Requires explicit workload opt-in, unexpired policy, matching context-bound namespace UID, Deployment UID and failed template hash.
2. Refuses recognized Argo CD/Flux tracking, paused/deleting/scaled-to-zero workloads and unobserved generations.
3. Requires the observed `Progressing=False / ProgressDeadlineExceeded` condition. A single pod restart never triggers repair.
4. Writes and flushes a private audit intent before any mutation.
5. Makes one JSON patch with UID and resourceVersion tests, image replacements and a persistent attempt annotation in the same request. A concurrent update causes refusal, not a forced overwrite.
6. The attempt annotation blocks further repairs, including from another process. After any attempt, an operator must inspect health and the audit before deliberately removing `devops-platform.io/recovery-attempt` and approving another repair. Do not automate latch removal.
7. Checks exact applied spec/UID and all desired replicas updated, ready and available across three observations, five seconds apart. Changes during verification stop the check. Timeout defaults to 180 seconds, configurable from 30 to 600.
8. A timeout, lost API response or process interruption can leave the change applied. Inspect live state and the attempt annotation before retrying; never infer that an error means no mutation occurred.

Exit codes: `0` eligible preview or observed Deployment readiness; `1` recovery readiness timeout; `2` refusal/error or uncertain outcome. Readiness does not prove business-level recovery. Verify service traffic, error rates and data integrity separately.

## Permissions

Use a dedicated credential with `get` on the specific namespace, and `get`/`patch` on the named Deployment. Restrict Deployment RBAC with `resourceNames`. Kubernetes RBAC cannot restrict patches to image fields; this tool's policy is an additional guard, not a security boundary against a compromised credential. Do not grant cluster-admin. No pod delete, exec, secret read, node mutation or cloud provisioning is needed for recovery.

Diagnosis uses namespace-scoped list access for pods, deployments, events, PVCs, HPAs and Jobs. Optional node diagnosis needs list nodes. Missing permissions produce partial results.

## Validation status

Implementation and mock test cases are included. Tests and live recovery drills have not been run, following the project owner's request to verify later. This feature is not production-validated. Before enabling a scheduler, validate on an isolated cluster: dry-run/no writes, mismatched identity, expired policy, GitOps refusal, simultaneous attempts, patch conflict, lost response, image-pull failure, successful recovery, failed recovery, audit failure and application-level health. Confirm a second invocation cannot repeat the mutation.

## Automatically detect and recover one approved rollout

Prepare the same policy and workload opt-in as above. Start the monitor while the approved pod template is deployed, before or after the rollout fails. The hash binds the policy to that exact template; it cannot be prepared against an unrelated older template.

Preview mode waits and shows the repair it would make:

```bash
python -m devops_toolkit watch-recovery --policy /secure/recovery-policy.json
```

Enable automatic execution for the approved rollout:

```bash
python -m devops_toolkit watch-recovery --policy /secure/recovery-policy.json \
  --execute --audit /secure/reports/recovery-UNIQUE-RUN-ID.jsonl
```

The audit directory must already exist and the filename must be new. The monitor runs in the foreground on the host where you start it; closing that process stops monitoring. It does not configure a system service, alerts or cluster credentials.

- Polls every 15 seconds by default (`--interval 5..60`).
- Requires three consecutive observations of an observed-generation `ProgressDeadlineExceeded` condition. A normal pod restart is not a trigger.
- Exits without repair if all desired replicas are updated, ready and available. Kubernetes readiness remains a limited signal, not a business-health guarantee.
- Waits up to 900 seconds by default (`--max-wait 30..3600`). The recovery verification window is additional, default 180 seconds (`--recovery-timeout 30..600`). API calls can add their bounded request timeouts.
- Rechecks policy expiry, identity, exact template, opt-in, GitOps tracking and the persistent attempt latch on each poll. Policy edits stop the monitor; recovery also rechecks the approved policy hash before proceeding.
- On the failure trigger, invokes the existing recovery command exactly once. Recovery re-reads the live target and performs its conditional patch. A conflict or an uncertain response stops the process; there is no repair retry loop.
- Missing API access, changed target, an existing attempt latch or a changed/expired policy stops monitoring. Do not configure automatic process restarts to bypass these stops.

Monitor exit codes: `0` ready without repair, eligible preview, or successful recovery verification; `1` monitoring/recovery timeout; `2` refusal, interruption or error. Console output distinguishes these outcomes. The private audit file is created only when repair is triggered; monitoring-only observations go to stdout. Preserve stdout and route nonzero exits to your own alert system before unattended use.

A monitor is not enabled in this repository by default. Running the execute command requires a configured cluster, approved policy and workload opt-in. No cluster is connected here, and no monitor has been started. Mock test cases are supplied but have not been executed, following the request to verify later.
