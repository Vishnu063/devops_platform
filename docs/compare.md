# Compare snapshots: what changed?

When a release or incident happens, engineers often compare many command outputs manually. This command compares the saved, selected fields and points out differences.

It runs offline. It does not connect to Kubernetes, read kubeconfig, change anything in the cluster or upload files.

## Try a sample

From the repository root, with Python 3.12:

```bash
python -m devops_toolkit compare examples/snapshots/before.json examples/snapshots/after.json
```

The example snapshots are invented and clearly labeled. Their image digests are not usable releases. They demonstrate the output format, not a successful test run.

Illustrative output:

```text
CHANGE deployment/platform: Image references changed | [...]
CHANGE deployment/platform: ready replicas changed | 3 -> 1
CHANGE pod/api-old-1/api: Restart counter increased | 0 -> 4
CHANGE event/api-old-1: Warning first captured: BackOff | null -> 4
```

Read this as: the version changed, fewer replicas are ready, restarts rose and a warning appeared in the captured data. Investigate those clues; they do not prove a cause.

## Use it with your cluster

Before the release:

```bash
python -m devops_toolkit incident --context YOUR_CONTEXT --output reports/before
```

Afterwards, or when the problem appears:

```bash
python -m devops_toolkit incident --context YOUR_CONTEXT --output reports/after
python -m devops_toolkit compare reports/before/report.json reports/after/report.json
```

Collection needs approved cluster access; comparison does not. Both snapshot commands use the default platform namespace. Add `--namespace YOUR_NAMESPACE` to both if needed.

To save comparison results:

```bash
python -m devops_toolkit compare reports/before/report.json reports/after/report.json --output reports/comparison.json
```

The output must be a new file; its parent directory must exist. It is created with owner-only file permissions.

## What it compares

| Field | How to interpret a change |
| --- | --- |
| Deployment/pod image references | A different image is recorded |
| Desired, ready and updated replicas | Rollout or availability state changed |
| Container restart counter | An increase is worth investigating |
| Container readiness and reason | Health or waiting/termination state changed |
| Pod UID | The pod was replaced; restart counters are not compared across replacement |
| Warning event identity/count | A warning series first appeared or its observed count rose |
| Records missing from either file | Not captured; deletion is not assumed |

Only common pod/container identities get restart comparisons. New pod names are reported separately; the tool does not invent a total restart delta across a rollout. Reduced counters are marked as resets rather than improvement.

New snapshots store pod and event UIDs. Older snapshots without them are accepted with warnings about uncertain identity. Event counts are counters in retained event series, not a complete count of every incident.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Comparison completed |
| 1 | Differences found and `--fail-on-change` was supplied |
| 2 | Invalid input, mismatched scope, wrong time order or file error |

`--fail-on-change` is useful for scripts. A code 0 result does not certify that the application is healthy.

## Limits

- Both files must be schema-version-1 incident reports, with the same context name and namespace, in chronological order.
- Context names are compared as labels; the tool cannot prove that a kubeconfig context still points to the same physical cluster.
- Only captured fields are compared. Logs, annotations, environment variables and arbitrary extra fields are not copied.
- Partial/truncated collections are flagged. Snapshot limits can hide changes.
- Snapshots are observations taken at different times, not atomic cluster backups.
- Runtime image IDs, exact per-container image mapping, scheduler decisions and automatic root-cause analysis are outside this version.

Implementation: `devops_toolkit/compare.py`. Regression tests: `tests/test_compare.py`. Tests and real-cluster verification remain pending.

New incident snapshots include a Deployment pod-template fingerprint. When both snapshots contain it, comparison highlights a changed fingerprint even if image and replica counts stayed the same. It does not print template values or infer which field caused the change. Legacy snapshots without this field remain accepted.
