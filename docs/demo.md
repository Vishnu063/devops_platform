# See automatic recovery on a local cluster

The demo includes four isolated scenarios: bad image, incorrect Service selector, reduced replicas and broken readiness configuration. Each supplies a known approved correction and attempts it once. When run, it produces a readable report from live observations. It is not a general-purpose Kubernetes auto-healer.

**Current evidence:** regression tests passed locally, and disposable live scenarios have run on isolated GitHub runners. See [compatibility](compatibility.md) for the initial outcomes, selector correction and rerun. Local Docker/kind/kubectl are unavailable in the editing workspace; no production cluster is used.

## Fastest way: run it on GitHub

1. Open **Actions → Local recovery demo → Run workflow** in this repository.
2. Choose the branch and scenario you want to verify and run the workflow.
3. Open its summary and download **local-recovery-evidence**.

The workflow supports manual selection and a four-scenario matrix on main-branch changes to `devops_toolkit/demo.py` or its workflow file. It creates a kind cluster on an Ubuntu GitHub runner, runs focused offline checks and then attempts the real demo. It uses no AWS account, production kubeconfig or repository secret. It does not deploy the platform application. A green result applies only to the commit and isolated scenario that ran. Use [the run evidence](compatibility.md) rather than assuming every scenario passed.

## Run on your laptop

Prerequisites:

- Python 3.12 or later.
- Docker installed and running with a local daemon.
- kind v0.33.0 and kubectl v1.37.x on PATH. The demo uses a pinned Kubernetes v1.37.0 node image.
- Linux amd64, or an amd64 Docker Desktop environment. The pinned Python image matches this repository's amd64 runtime. ARM hosts are refused by this demo.
- Internet access for the node and Python image pulls. Allow several GB of available disk and enough spare memory for a local Kubernetes node.

Install tools using the [kind guide](https://kind.sigs.k8s.io/docs/user/quick-start/), [Docker guide](https://docs.docker.com/engine/install/) and [kubectl guide](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/). The demo does not install host tools, use sudo or ask for cloud credentials.

From the repository root:

```bash
python -m devops_toolkit demo
```

Or use `make demo`. You do not need to install Flask, scanners or Terraform to run this standard-library demo.

The command creates a new randomly named `devops-demo-*` kind cluster and a private kubeconfig inside its evidence folder. It does not accept an existing context, merge kubeconfig into your normal file, or patch workloads in an existing cluster. It refuses remote Docker endpoints. Do not run it on a host without enough local resources.

## What happens

1. Check local prerequisites and the Docker daemon.
2. Create a separate cluster with a pinned node image.
3. Deploy a restricted nonroot Python HTTP server and an internal ClusterIP Service.
4. Verify rollout readiness and the expected HTTP response; save the healthy snapshot.
5. Set an intentionally nonexistent image digest on the demo Deployment only.
6. Wait for the controller to report an observed-generation `ProgressDeadlineExceeded`; save the failed snapshot.
7. Generate a short-lived recovery policy binding this exact namespace UID, Deployment UID and failed pod template to the known healthy image.
8. Start `watch-recovery --execute`. After three failure observations, it makes one conditional image repair, sets the attempt latch and checks readiness.
9. Verify the approved image, audit evidence and expected HTTP response. Confirm another recovery invocation is refused before a new audit is opened.
10. Save the recovered snapshot and a readable failed-versus-recovered comparison.
11. Remove this demo's cluster and write a PASS/FAIL summary based on the completed stages.

The sample deliberately preserves the old healthy replica during the failed rolling update. It demonstrates failed-release recovery; it does not prove zero downtime, sustained availability or recovery from a total outage. HTTP requests go through the Kubernetes API Service proxy and do not validate external ingress, DNS, NetworkPolicy or load-balancer traffic.

The approved image and node image are pinned. The node pin comes from [the kind v0.33.0 release](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0). The Python image is the existing repository CI pin. This demo does not prove image-signature enforcement.

## Read the evidence

The command prints its private evidence folder, normally `reports/demo-UNIQUE-ID/`:

| File | What it shows |
| --- | --- |
| `summary.md` | Readable PASS/FAIL stage table |
| `results.json` | Run ID, time, image pins, observed stage outcomes and cleanup status |
| `before/report.json` | Healthy workload snapshot |
| `failed/report.json` | Failed rollout snapshot |
| `after/report.json` | Recovered workload snapshot |
| `comparison.txt` / `comparison.json` | Observed changes between failure and recovery |
| `recovery.jsonl` | Durable repair intent, patch acknowledgement and readiness outcome |
| `monitor.txt` | Monitor output after successful execution |
| `recovery-policy.local.json` | Private, short-lived approval for this demo |
| `kubeconfig.local` | Private local-cluster credentials; do not share |

The GitHub workflow uploads only the listed summary/results, recovery audit, comparison and successful monitor output. It excludes kubeconfig, policy and raw snapshots. Logs and Secret values are not collected by the demo. Review evidence before sharing it. `reports/` is ignored by Git.

A FAIL means a stage did not complete. It is never converted into a PASS by cleanup or by a later retry. The tool makes no second repair attempt. A report is evidence only when generated by a real run; this repository does not include fabricated successful results.

## Keep the cluster to inspect it

```bash
python -m devops_toolkit demo --keep-cluster --output reports/my-demo
```

The output folder must be new. Inspect using its dedicated kubeconfig, replacing the printed cluster suffix:

```bash
kubectl --kubeconfig reports/my-demo/kubeconfig.local --context kind-devops-demo-PRINTED_SUFFIX -n devops-demo get pods
```

When finished, delete only the exact demo cluster name printed in `results.json`:

```bash
kind delete cluster --name devops-demo-PRINTED_SUFFIX --kubeconfig reports/my-demo/kubeconfig.local
```

Normal runs clean up automatically on success, failure or a handled interrupt. A killed process, host failure or failed cleanup can leave the local cluster behind; inspect the recorded cluster name and remove that exact cluster. Avoid broad Docker prune commands.

Exit codes: `0` completed demo and requested cleanup; `1` failed stage or failed cleanup; `2` missing prerequisites or unusable output path. Image pulls, Docker access and API failures can prevent completion even if the toolkit logic is correct.

## What this verifies and what remains

A successful live run demonstrates only the selected scenario, API-proxy HTTP checks, audit evidence and repeated-invocation refusal. It does not verify all possible container fields, Argo CD self-heal, production permissions, concurrent controllers, cloud failures, upgrades or disaster recovery. Those need their own isolated drills before use.

The manual workflow also runs offline cases for preview/no mutation, changed policy, identity checks, GitOps refusal, conditional patches and bounded monitoring. Passing mocks does not replace live Kubernetes validation.

## Choose a scenario

| Flag | Deliberate fault | Known approved correction |
| --- | --- | --- |
| `--scenario images` (default) | Nonexistent image digest | Restore the pinned healthy image |
| `--scenario selector` | Service selector matches no demo pods | Restore the demo pod label selector |
| `--scenario replicas` | Two demo replicas reduced to one | Restore the approved count of two; refuse HPA ownership |
| `--scenario configuration` | Readiness probe points at a closed port | Restore the previously captured correct readiness probe |
| `--scenario all` | Run all four in sequence | Separate new cluster per scenario; stop after a failure |

`--scenario all` may take substantially longer and uses a new parent evidence folder. No attempt latch is cleared to reuse a workload. The configuration case deliberately breaks the probe while the server remains healthy; it does not claim that loosening probes repairs application failures. The selector case checks EndpointSlice readiness and the expected HTTP response; other network paths remain outside this drill.

Successful scenario completion also writes `timeline.md`. Service selectors are checked directly by the demo; standard namespace snapshots do not include Service objects, so a selector diff is not fabricated in the snapshot comparison. Repair audit events identify that action in the timeline. Observed scenario outcomes, including failures and reruns, are recorded in [compatibility](compatibility.md).
