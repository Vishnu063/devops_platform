# Collect evidence for one Deployment

Use a workload bundle when an engineer needs relevant evidence from one application rather than an entire namespace:

```bash
devops-toolkit bundle --context YOUR_CONTEXT --namespace platform \
  --deployment YOUR_DEPLOYMENT --output reports/workload-UNIQUE-ID
```

The output directory must be new. The command reads the Deployment UID, finds controller-owned ReplicaSets, then finds their controller-owned Pods. Similar labels alone do not include unrelated Pods. Events are filtered by the known workload/compatible-Service object UIDs. Services are selected by selector compatibility with the pod template; this is not proof of exclusive ownership or traffic correctness.

## Files

| File | Contents |
| --- | --- |
| `report.json` | Selected pod state/restarts, Deployment state/template fingerprint and scoped event reasons |
| `workload.json` | Selected Deployment/ReplicaSet identities and compatible Service port metadata |
| `README.md` | Collection status and sharing reminder |
| `log-*.txt` | Only when explicitly requested; bounded current regular-container logs |

The report follows the existing incident snapshot format with workload scope metadata, so it can be compared or used in a [timeline](timeline.md). No raw Deployment/Pod specs, Secret/ConfigMap objects, environment values, annotations or event messages are dumped. Selected pod count defaults to ten; `--max-pods 1..50` controls it. Up to 100 selected events/Deployment records and 100 ReplicaSet/Service metadata records are retained. Counts expose truncation; inspect them before assuming completeness.

## Optional logs

Add `--include-logs` only when you need them. Existing incident limits apply: current regular containers, up to three containers per pod, 50 lines/10 minutes/64 KiB per request and 20 log requests overall. Previous-container logs are not included. Redaction is best effort; logs can still contain credentials or personal information. Review them before sharing.

Directories are private (0700), files private (0600). No bundle is uploaded, archived to public CI or sent in an alert. Reports and logs stay local. No cluster state is changed.

## Permissions and incomplete evidence

The identity needs the target Deployment and namespace reads, namespace list access for ReplicaSets, Pods, Services and events, and optional pods/log access. The [diagnostics role template](../examples/rbac/diagnostics-role.yaml) now includes ReplicaSets; bind/review it as appropriate and add namespace metadata access separately.

If ReplicaSet reads fail, the tool does not fall back to broad label matching. It records the unavailable data and cannot establish a complete pod scope. Missing API access and log failures produce partial evidence. Zero selected pods is not a healthy-status claim. API reads are not atomic; workloads can change during collection.

Exit `0` means scoped evidence was collected, not that the application is healthy. Exit `2` means partial collection or an input/access/output error. Code and mock cases are included; no real bundle has been collected in this revision.
