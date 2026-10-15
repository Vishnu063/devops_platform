# DevOps toolkit: start here

This toolkit helps with three everyday jobs:
1. Find obvious problems before a deployment.
2. Collect a useful snapshot before a release or when an application is unhealthy.
3. Compare snapshots to see what changed.

It runs on your machine using Python. Preflight and collection use existing kubectl access; comparison reads local files only. It does not install anything in the cluster, deploy, delete, roll back, switch contexts or upload reports.

**Status:** implemented, with tests supplied for later execution. Live cluster behavior has not been verified.

## What you need

- Python 3.12 on Linux. The CLI itself uses only the standard library.
- kubectl installed and connected to a cluster you are allowed to inspect.
- The correct context name. List names with `kubectl config get-contexts -o name`.
- Optional: Docker and registry login if you want to check whether images are accessible.

Replace `YOUR_CONTEXT` in the commands below. Explicit context selection helps avoid inspecting the wrong cluster.

## 1. Check before a deployment

```bash
python -m devops_toolkit preflight --context YOUR_CONTEXT --namespace platform --deployment platform
```

By default this inspects the **existing Deployment**. It does not see changes still on your laptop.

| Check | What it means |
| --- | --- |
| Namespace | Does the target namespace exist? |
| Image | Does each image use a full SHA-256 digest? |
| Resources | Are CPU/memory requests and limits set, and do requests fit their limits? |
| Health | Are readiness and liveness probes present? |
| References | Do required Secret/ConfigMap objects and referenced data keys exist? |
| Capacity | Is there estimated CPU/memory room for one new pod? |

Secret values are never written to the report. Reference checks ask kubectl to print only object names and key names. This still requires permission to get the Secret object.

To inspect the image in its registry too:

```bash
python -m devops_toolkit preflight --context YOUR_CONTEXT --verify-images
```

This uses `docker manifest inspect` with your existing registry access. Inaccessible images produce UNKNOWN because a network or login failure cannot establish that an image is missing. It does not verify signatures.

To save results privately:

```bash
python -m devops_toolkit preflight --context YOUR_CONTEXT --output reports/preflight.json
```

Create the parent reports directory first. The output file must be new; existing files are never replaced.

### Check a proposed change

Export the intended Deployment as JSON. For example, for a single Deployment YAML file:

```bash
kubectl --context YOUR_CONTEXT --namespace platform create --dry-run=client --validate=false -f deployment.yaml -o json > desired.json
python -m devops_toolkit preflight --context YOUR_CONTEXT --file desired.json
```

The first command converts the file without creating the resource; kubectl may still perform API discovery. The toolkit also accepts a JSON List containing one matching Deployment. Supply the correct name with `--deployment`. Treat the exported file as private if it contains inline environment values; do not commit it.

### Read the result

Illustrative output only:

```text
PASS    namespace: Target namespace exists
PASS    image:api: Digest is set
FAIL    reference:secret/app-token: Required object or data key is missing
UNKNOWN capacity: Capacity cannot be estimated with available access/resource types
WARN    admission: Admission policies and signatures are not evaluated by this tool
```

| Exit code | Meaning | What to do |
| --- | --- | --- |
| 0 | No detected blockers or unknown required checks | Review warnings; this is not deployment approval |
| 1 | One or more definite configuration problems | Fix them and rerun |
| 2 | Incomplete inspection, bad input or access/tool failure | Investigate; do not assume success |

Capacity uses declared requests, ordinary init-container requests, pod overhead, ready nodes, node selectors and currently assigned pods. It conservatively excludes tainted nodes. Pod-level resource budgets or restartable init containers produce UNKNOWN. It does not reproduce the Kubernetes scheduler: affinity, topology, quotas, volumes, ports, pending reservations and a full rollout remain outside the estimate.

## 2. Collect incident evidence

```bash
python -m devops_toolkit incident --context YOUR_CONTEXT --namespace platform
```

This creates a new private directory under `reports/`. Open its `report.json`.

The report includes:
- Selected pod health, container reasons and restart counts; unhealthy pods are prioritized.
- Deployment generation, ready/updated counts and image references.
- Recent event types, reasons, counts and affected object names.
- Any resources the tool could not read.

Environment values, annotations, Secret objects and event messages are excluded. A snapshot provides evidence, not a diagnosis.

For a custom directory:

```bash
python -m devops_toolkit incident --context YOUR_CONTEXT --output reports/my-incident
```

If needed, explicitly include recent logs:

```bash
python -m devops_toolkit incident --context YOUR_CONTEXT --include-logs
```

Logs are limited to 50 lines, the last ten minutes, and 64 KiB per request. At most 20 current-container logs are collected, across at most three containers per selected pod. No previous-container logs are collected in this version.

Common credential formats are redacted, but redaction cannot guarantee that every sensitive value is removed. Review files before sharing. Nothing is uploaded automatically. Files use owner-only permissions; the report directory is private. A partial collection returns exit code 2 and lists missing data.

## Permissions

| Action | Access needed |
| --- | --- |
| Preflight configuration | Get namespace; get Deployment unless using a local JSON file |
| Required references | Get each named Secret/ConfigMap |
| Capacity estimate | List nodes and list pods across all namespaces |
| Incident snapshot | List pods, Deployments and events in the target namespace |
| Optional logs | Get pods/log in the target namespace |

Use existing approved credentials. Do not grant cluster-admin just to run this tool. Missing permissions are reported rather than silently treated as a pass.

## How the code works

`devops_toolkit/cli.py` contains:
- `Kube`: explicit-context kubectl queries, timeouts and sanitized errors.
- `quantity` / `pod_requests`: CPU and memory request arithmetic.
- `preflight`: checks and PASS/FAIL/UNKNOWN/WARN records.
- `incident`: allowlisted evidence and optional logs.
- `redact` / `write_private`: best-effort log redaction and exclusive private file creation.
- `main`: command options and exit codes.

Commands use argument arrays without a shell. Kubernetes writes are not implemented. Outputs and kubeconfig access stay on your machine.

## Practice later

1. Run preflight against the lab.
2. In a local proposed manifest, reference a missing Secret. Observe FAIL without changing the cluster.
3. Collect a snapshot during a lab rollout and compare desired versus ready replicas.
4. Explain why missing permissions produce UNKNOWN and why a capacity estimate is not a scheduling guarantee.

Regression tests are in `tests/test_toolkit.py`. They use fake cluster data and mocked processes. The existing test discovery command includes them; they have not been run during implementation. The current coverage threshold measures the API package, not toolkit coverage.

## 3. Compare snapshots

```bash
python -m devops_toolkit compare before/report.json after/report.json
```

Comparison needs no cluster or credentials. It highlights observed changes in images, replica counts, pod state, restarts and warning events. Use `--output reports/comparison.json` for a new private JSON file, or `--fail-on-change` to return exit code 1 when differences are found. Invalid or incompatible snapshots return 2. Normal successful comparison returns 0, even when differences exist.

See [the comparison guide](compare.md) for the full before/after workflow and limitations.
