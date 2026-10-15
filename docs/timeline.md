# Understand an incident in time order

Use saved snapshots to see observed symptoms and changes, then add the repair audit to see what action was attempted and whether readiness was confirmed. This command is offline and never contacts Kubernetes or sends notifications.

```bash
devops-toolkit timeline before/report.json failed/report.json after/report.json \
  --audit reports/recovery.jsonl --output reports/timeline.md
```

Use `--audit` repeatedly for additional repair audits. Snapshots are sorted by timezone-aware capture time and must share context/namespace. Up to 50 snapshots and 50 audits are accepted; each input is size limited. Output is a new private file. With no output path, the terminal receives escaped JSON rather than untrusted Markdown/control characters. `--format json` writes a JSON timeline.

The timeline shows:

- Snapshot capture times and selected non-running/not-ready evidence.
- Captured container failure reasons.
- Image, replica, restart, readiness and warning-event differences between successive snapshots.
- Scoped repair intent, patch acknowledgement, readiness confirmation, timeout or unknown outcome.

Audit event names have precise meanings. `patch_acknowledged` confirms an API response, not application recovery. `deployment_ready`/`readiness_confirmed` describe the implemented readiness checks. `outcome_unknown` requires inspection; never retry blindly. An intent without a terminal event is explicitly marked unknown.

New repair audits include context and namespace. Legacy audits without scope are skipped with a warning; a filename alone cannot establish which cluster they describe. Cross-scope audit inputs are rejected. The timeline does not copy arbitrary audit fields, policy contents, logs or Secret values.

A change timestamp is when it was observed in a snapshot, not the exact moment it happened. Context names can be reused. Review physical-cluster identity, namespace UID and workload UIDs before relying on correlation. Partial captures are flagged and absence does not prove deletion. A timeline does not prove root cause or business recovery.

The four demo scenarios generate `timeline.md` automatically when all stages complete. No example is presented as a real successful run. Exit `0` means a timeline was produced; `2` means invalid/unreadable/mismatched evidence or an unusable output path. Tests and live validation remain pending.

New Deployment snapshots include a pod-template fingerprint, so readiness/resource-only template changes can be observed without copying configuration values. A changed hash still requires inspection of the reviewed spec diff. Service objects are not part of standard incident snapshots; the selector demo verifies its own Service change directly rather than fabricating a selector diff.
