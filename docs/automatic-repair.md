# Automatic repair, explained simply

The toolkit watches one exact approved failure, applies one known correction, then checks Kubernetes readiness. It does not discover a universally correct fix. A policy is authorization: protect it like deployment credentials. Default mode is preview. Nothing has been deployed or enabled here.

## What can be repaired?

| Area | What happens automatically after setup | What still needs an engineer |
| --- | --- | --- |
| Failed deployment | Existing image rollback; new approved container-field restoration | Application bugs, schema compatibility and choosing a trusted replacement |
| CI/CD | Existing pipeline tests/scanners block unsafe releases | Broken code/tests, runner incidents and dependency changes; no automatic reruns added |
| Kubernetes workload | Restore approved image/resources/probes on an observed failed rollout | Running-pod failures without a failed rollout, nodes and cluster components |
| Configuration | Restore approved container environment references; optional GitOps self-heal | Missing Secret/ConfigMap objects, wrong secret values, configuration outside supported fields |
| Networking | Restore a known ClusterIP Service selector, then check ready EndpointSlices | DNS, CNI, ingress, certificates, target-port errors and NetworkPolicies |
| Capacity/storage | Restore accidentally lowered replicas within approved limit | Node capacity, memory leaks, PVCs, disks and data recovery |
| Security/access | Restore reviewed container securityContext on a failed rollout; existing release scan gates | Credential rotation, RBAC changes, vulnerability fixes and incident containment |
| Troubleshooting | Existing diagnosis, snapshot collection and offline comparison | Confirming root cause and application/business health |

## Configure a repair on an isolated non-GitOps lab workload

1. Use Python 3.12, kubectl and a trusted kubeconfig with an explicit context. Grant least privilege: get the target and namespace, patch only the named Deployment or Service. Replica repair additionally needs list HPA access; Service verification needs list EndpointSlices. API admission and RBAC are the final enforcement boundary.
2. Exclude other operators/controllers managing the target. HPA detection is built in for replica repair, but there is no universal check for KEDA, custom controllers or future HPA creation. GitOps detection recognizes standard labels/annotations; absence of tracking is not proof of no controller. Do not give multiple reconcilers authority over the same fields.
3. Explicitly annotate the chosen target. For a Deployment named `platform`:

```bash
kubectl --context YOUR_CONTEXT -n platform annotate deployment platform devops-platform.io/allow-repair=true
```

Use `service` for a Service. Do not annotate the repository's Argo-managed Deployment for direct repair.

4. Copy `examples/repair-policy.json` to a private path outside Git. It is deliberately invalid until populated. Fill in context, namespace/name, exact kind (`Deployment` or `Service`), live UIDs, a short UTC expiry, the SHA256 of the live **whole spec**, and your reviewed fix. You can inspect identities and hash without exporting a full spec to disk:

```bash
kubectl --context YOUR_CONTEXT get namespace platform -o jsonpath='{.metadata.uid}'
kubectl --context YOUR_CONTEXT -n platform get deployment platform -o json | python -c 'import sys,json; from devops_toolkit.recovery import fingerprint; d=json.load(sys.stdin); print("uid:",d["metadata"]["uid"]); print("failed_spec_sha256:",fingerprint(d["spec"]))'
```

Run from the repo root. Replace resource kind/name for a Service. Do not commit policies, credentials, live specs or audit records. Use mode 600 and a private parent directory. A failed-state policy authorizes that exact state only; a new release/spec change requires a new reviewed policy. This deliberately cannot silently accept arbitrary future failures.

5. Choose one action per policy:

- `containers` with kind `Deployment`: `approved` maps existing regular-container names to approved fields. Allowed fields: image (digest only), resources, env/envFrom references, readiness/liveness/startup probes, securityContext. Only the named fields change; whole field values replace existing values. Init containers, commands, volumes and Pod-level settings are excluded. Env entries must use valueFrom references, never plaintext values. Missing referenced objects are not created. A current-generation ProgressDeadlineExceeded signal is required. Resource changes need verified quota/capacity; raising a limit does not fix a leak. Restoring probes must not hide a failure. Security policies remain subject to admission controls.
- `replicas` with kind `Deployment`: `approved` is an integer from 1 through 10. Current replicas must be above zero and below that value. Zero may be intentional, so it is refused. No downscaling, no new nodes, no quota/capacity guarantee. HPA ownership or inability to list HPAs is refused. An explicit count drift is the trigger; the tool does not infer desired replicas from CPU use. Choose an affordable count for your environment.
- `selector` with kind `Service`: `approved` is a nonempty label map, for example `{"app.kubernetes.io/name":"platform"}`. Only ordinary ClusterIP Services without publishNotReadyAddresses are accepted. Selectors determine traffic destinations: verify the exact intended pods before approving. No port, IP, type, DNS or ingress changes. Verification requires a ready, nonterminating endpoint on a slice owned by the target Service; it is not an HTTP or routing test.

Preview the exact policy while monitoring:

```bash
python -m devops_toolkit repair --policy /secure/repair-policy.json
```

After reviewing that policy, enable its single automatic attempt:

```bash
python -m devops_toolkit repair --policy /secure/repair-policy.json \
  --execute --audit /secure/reports/repair-UNIQUE-RUN-ID.jsonl
```

The audit directory must exist and the filename must be new. No interactive prompt is used. The patch tests UID and resourceVersion, so simultaneous writes conflict. Successful patches set the persistent `devops-platform.io/repair-attempt` annotation atomically with the repair. Never remove this latch automatically. A lost response, rejected patch, timeout or failed verification stops the command; it does not retry the mutation. An operator must inspect live state and audit before any new authorization.

Monitoring defaults: 15-second interval, three consecutive eligible observations, 900-second window, followed by up to 180 seconds of readiness verification. Flags: `--interval 5..60`, `--max-wait 30..3600`, `--timeout 30..600`. Policy edits, expiry, UID/spec changes and API failures stop monitoring. Deployment verification requires the same applied spec and all desired replicas updated, ready and available in three observations. Admission changes cause refusal after the patch; inspect live state. These are limited readiness signals, not end-to-end health guarantees.

Exit codes: 0 = eligible preview, already-ready rollout, or confirmed readiness (stdout distinguishes); 1 = timeout; 2 = refusal/error/interruption. Route nonzero exit codes to your alert system. No alert destination, service, CronJob or automatic process restart is installed. Run on a trusted management host; do not automatically restart failed repair processes or reuse old authorization to bypass a stop.

## GitOps-managed workloads: let Argo CD own repair

An optional `gitops/self-heal-patch.yaml` enables automatic sync and self-heal without pruning. It is a merge patch, not a standalone manifest. After validating your pinned release and Git content, review and apply explicitly:

```bash
kubectl --context YOUR_CONTEXT -n argocd patch application devops-platform \
  --type=merge --patch-file gitops/self-heal-patch.yaml
```

This follows approved Git content, including future main-branch commits; enforce release review and branch protection before enabling. It can restore drift in managed Deployment, Service and configuration fields. It does not identify a bad desired release, repair data or fix infrastructure outside the application. Correct a bad desired release through a reviewed Git change. Automated sync and direct rollback must not fight each other. The existing default Application manifests remain manual. The overlay has not been applied.

## Verification still pending

Per the request to verify later, this change includes mock regression cases and static syntax checks only. Before unattended use, run the suite and isolated cluster drills for preview, expiry, policy editing, GitOps/HPA refusal, identity/spec changes, simultaneous repairs, API response loss, admission mutation, audit failure, wrong selectors, quota failures, healthy and failed recovery. Verify application traffic separately. No production-readiness claim is made.

Primary references: [Kubernetes Deployment behavior](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/), [HPA](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/), [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/), [Argo CD automated sync](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/).

## Try recovery on a separate local cluster

Run `python -m devops_toolkit demo` after installing local Docker, kind and kubectl, or manually run the **Local recovery demo** GitHub workflow. It introduces one failed image, attempts approved recovery, checks HTTP and records the result. Read [demo setup and evidence](demo.md). The implementation is supplied; live validation remains pending.

## Easier setup and operation

Use [the policy generator](policies.md) instead of manually copying UIDs/hashes. [Release-check](release-check.md) explains pre-deployment evidence, [timeline](timeline.md) correlates snapshots/audits and [alerts](alerts.md) provides optional completion notifications. Direct repairs now honor [namespace pause and process stop controls](operations.md); these are checked before planning and immediately before mutation but cannot atomically cancel an API request already in flight. See [compatibility](compatibility.md) for current execution evidence.
