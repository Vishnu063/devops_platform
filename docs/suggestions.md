# Get suggestions when something fails or gets stuck

Use `suggest` to get a short investigation path, possible causes, resolution guidance and a verification step. It works offline and never runs the suggested actions.

```bash
# Start with a known symptom.
devops-toolkit suggest --issue CrashLoopBackOff
devops-toolkit suggest --issue ImagePullBackOff
devops-toolkit suggest --issue Pending
devops-toolkit suggest --issue stuck

# Or use evidence you already collected.
devops-toolkit suggest --report private-reports/diagnosis.json

# Save private suggestions and optionally make them readable in a browser.
devops-toolkit suggest --report private-reports/diagnosis.json \
  --output private-reports/suggestions.json
devops-toolkit report private-reports/suggestions.json \
  --output private-reports/suggestions.html

# Discover supported issue areas.
devops-toolkit suggest --list
```

Issue areas cover crashes, image pulls, memory, configuration references, scheduling/capacity, probes/rollouts, Services, storage, autoscaling, permissions/admission, recovery guards and toolkit prerequisites/input/output problems. Unknown symptoms receive an evidence-collection/escalation path, not a guessed fix. `--format json` is available for scripts.

## What you will see

For an image-pull symptom, the helper suggests checking the exact image digest, registry access and node pull credentials, then verifying that the intended image starts and becomes ready. It does not assume that every image-pull failure means the image is missing.

Each issue area includes:

1. **Possible causes** — hypotheses to check, not a root-cause claim.
2. **Next steps** — inspect evidence, confirm the cause and use a reviewed correction.
3. **Verification** — confirm intended state and application behavior after your fix.
4. **Escalation boundary** — involve the workload/platform owner when evidence is incomplete, investigation stalls or a mutation outcome is unknown.

Suggestions are deterministic, rule-based guidance. They do not search the web, call an AI service, inspect raw logs or contact a cluster. Use your platform's version-specific runbook for checks outside their scope.

## Where suggestions appear automatically

`diagnose` findings now include a `suggestion_command` for more detailed help. Readable diagnosis/release/configuration reports link a finding to its matching help topic. Original JSON fields and exit codes are retained; these are additive hints.

When an operational toolkit command returns exit 1 or 2, the top-level CLI prints a suggestion hint to stderr. Diagnosis/release/configuration commands with `--output` suggest using that report **if it was saved**. Recovery commands point to recovery guidance rather than an automatic retry. No raw error output, credential, command arguments or live object fields are copied into the suggestion report.

A running/hung command cannot print a completion hint until it returns. Open another terminal and use `suggest --issue stuck` if needed. This feature does not introduce a background watchdog or cancel in-flight API operations. Never assume that interrupting a repair means its patch was not applied.

## Important limits

- A suggestion is not authorization to repair a cluster, override an owner, grant privileges or clear an attempt latch.
- Missing data may be caused by access, connectivity or collection errors; it does not prove a permission problem or missing object.
- Historical events/last states may describe an earlier failure. No matched symptom is not a health guarantee.
- For uncertain repair outcomes, inspect the scoped audit and live identity/state; do not replay the mutation blindly.
- Use new output files under an existing private directory. Outputs contain curated playbook text and topic names; source report values are not copied. Review original evidence privately.
- Exit 0 means suggestions were produced, not that anything was fixed. Exit 2 means input/output processing was incomplete.

Suggestion regression cases and installed CLI processing of a synthetic report have passed. See [compatibility](compatibility.md) for exact scope. Suggestions themselves do not execute repairs, cluster checks or notifications.
