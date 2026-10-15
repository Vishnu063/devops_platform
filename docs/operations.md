# Operate approved repairs

Nothing is installed, scheduled, deployed or enabled automatically. Use dedicated credentials, explicit context and a reviewed policy. Existing read-only commands stay read-only; the `demo` command intentionally creates and deletes its own local cluster only when a user runs it.

## Emergency stop

An operator can pause direct repairs in the target namespace using this annotation:

```bash
kubectl --context YOUR_CONTEXT annotate namespace platform \
  devops-platform.io/repairs-paused=true --overwrite
```

Remove the annotation only after review, or set it to the exact value `false` to resume. Invalid values fail closed. Monitors check this while planning and the execution paths re-read it immediately before mutation. Namespace identity must still match the approval.

The annotation check and Deployment/Service patch are separate API requests. A pause cannot atomically cancel a patch already in flight or undo an acknowledged mutation. For urgent incidents, stop the runner and revoke its write credential using your access-control procedure, then inspect the audit and live state. The pause does not disable independent controllers such as Argo CD, HPA or another user's scripts.

A process can also be started with `DEVOPS_TOOLKIT_DISABLE_REPAIRS=1`. That blocks direct repair paths. Changing a variable in another shell does not modify an already-running process; stop/restart the runner with that environment when appropriate. This setting does not stop `demo` from deliberately creating a local cluster, so do not run demos when you want no local changes.

## Permissions

[Direct-recovery RBAC template](../examples/rbac/direct-recovery.yaml) limits get/patch to named `platform` Deployments/Services, reads the one namespace, and lists HPAs/EndpointSlices needed by supported repairs. Replace target names, namespace, subject and binding names before review. It is a template, not an applied permission grant. The ServiceAccount has no mounted token by default; credential issuance and runner authentication are your responsibility. Separate identities/roles further when a runner needs only one repair type.

[Namespace diagnostics role](../examples/rbac/diagnostics-role.yaml) is optional and intentionally has no RoleBinding. Bind it only to the intended diagnostic identity. It grants no Secret data, pod logs, node reads, namespace metadata or cross-namespace capacity access.

Additional access is explicit:

| Feature | Additional permission |
| --- | --- |
| Read namespace metadata/stop state | `get` on the single cluster-scoped namespace |
| Required Secret/ConfigMap references | `get` on named Secrets/ConfigMaps; Secret get authorizes values even though this tool outputs keys only |
| One-pod cluster capacity estimate | `list` nodes and `list` pods across namespaces |
| Optional node diagnosis | `list` nodes |
| Opt-in incident logs | `get` pods/log in the namespace |
| HPA ownership guard | namespace `list` horizontalpodautoscalers |
| Service readiness | namespace `list` discovery.k8s.io EndpointSlices |

Do not grant cluster-admin to get a cleaner report. RBAC cannot limit an allowed Deployment patch to image fields: toolkit policies are application guards, not a security boundary against a compromised credential. Unknown third-party scaling/reconciliation controllers still require operator review.

## Interpret a repair run

Preserve its private audit and stdout. An intent is written and flushed before the single patch attempt. Conditional UID/resourceVersion tests prevent forced overwrites. Attempt annotations block repeated mutations after acknowledgement. Never automate latch clearing. A timeout, lost API response or interrupted process may leave a change applied; inspect live state before any new authorization.

Use [timeline](timeline.md) for correlated evidence and [alerts](alerts.md) for opt-in completion notification. No automatic process restart, external scheduler, alert destination or webhook is installed. Do not configure restarts to bypass a refused or uncertain repair.

## Compatibility and evidence

See [compatibility](compatibility.md) and [CHANGELOG](../CHANGELOG.md). All new behavior remains unexecuted for this revision. No production-readiness claim or service-level support promise is made.
