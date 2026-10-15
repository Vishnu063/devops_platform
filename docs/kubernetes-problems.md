# Kubernetes problems and recovery choices

Start with `diagnose`, then read the matching row. A symptom is not a proven root cause. Restarting a pod cannot repair bad code, a missing secret, an inaccessible registry or a broken storage system.

| Problem | Evidence to examine | Countermeasure | Toolkit automation |
| --- | --- | --- | --- |
| CrashLoopBackOff | Current/previous logs, termination status, configuration, dependencies | Fix application/configuration; restore approved image if release-related | Detect container status; conditional image recovery only after failed rollout |
| ImagePullBackOff / ErrImagePull | Registry image existence, pull identity, DNS/network | Correct digest, registry permissions or connectivity | Detect; approved image recovery may help a bad release, not broken credentials |
| Pending / FailedScheduling | Requests, quotas, node selectors, taints, affinity, PVC events | Right-size or add approved capacity; correct scheduling constraints | Detect Pending/events; preflight estimates capacity |
| OOMKilled | Memory metrics, limits, node pressure, heap profiles | Fix leak or review memory budget | Detect termination evidence; no automatic limit increases |
| Failed probes / NotReady | Probe settings, response time, dependencies | Fix endpoint, application or reviewed probe configuration | Detect readiness and Unhealthy events; no probe disabling |
| Failed rollout | Deployment conditions, observed generation, ReplicaSets | Restore compatible approved image or fix source manifest | `recover` supports one policy-bound image repair |
| HPA failures or limits | HPA conditions, metrics API, requests, configured bounds | Repair metrics or review scaling limits | Detect conditions; no uncontrolled scale-up |
| Node NotReady / pressure | Node conditions, kubelet/runtime, cloud health | Restore node or drain/replace after capacity and disruption checks | Optional node diagnosis; no drain, reboot or replacement |
| DNS / CNI / NetworkPolicy | DNS queries, CNI health, routes and network rules | Repair the specific failed network component or intended rule | Runbook only; no generic network-policy removal |
| Service / Ingress 502/503 | Selectors, EndpointSlices, readiness, ports, controller and upstream logs | Correct routing and restore healthy backends | Runbook only; workload readiness may provide supporting evidence |
| PVC / mount / attachment | PVC phase, StorageClass, CSI events, backend health | Restore provisioning/access; expand only supported storage after review | Detect PVC phase and mount events; never delete volumes |
| Missing configuration | ConfigMap/Secret references and key names | Restore approved configuration from its source | Preflight checks required references; diagnose reports config-error symptoms |
| RBAC / access denied | Exact failed verb, resource, namespace, identity | Grant only intended permissions through reviewed policy | Failed collection reported as unavailable; does not grant privileges |
| TLS / certificate renewal | Certificate expiry, issuer/order/challenge state, DNS | Repair issuer configuration and renewal with certificate manager | Runbook only; no TLS-secret generation or replacement |
| Failed Jobs / CronJobs | Job conditions, exit code, backoff, schedule/concurrency | Fix cause; retry only idempotent jobs | Detect failed Jobs; no automatic replay |
| API server / etcd / controller failure | Component health, quorum, provider status, backups | Follow provider/cluster disaster recovery procedure | Unavailable API is reported; no control-plane repair |
| Security / admission failures | Admission events, policy violation, scanner findings | Fix manifest/image or approved access policy | Some FailedCreate events detected; delivery scanners remain separate |
| GitOps drift / failed sync | Argo CD/Flux desired revision, diff, sync health | Correct Git and reconcile through the owning controller | Direct repair refuses recognized Argo CD/Flux ownership markers |

DNS, traffic, TLS, security, GitOps and control-plane checks are not implemented as active diagnostics. Historical events and `lastState` may refer to resolved incidents. Missing permissions and API failures produce partial results, never a clean-health claim.

## Why not automatically fix everything?

Different causes produce the same symptom. A crashing application can have a code bug, a missing dependency or a memory leak. Changing limits or restarting it without evidence can make the outage worse. Kubernetes already restarts containers and reconciles replica counts. This toolkit adds evidence and a narrowly scoped recovery path.

## Official references

- [Troubleshooting applications](https://kubernetes.io/docs/tasks/debug/debug-application/)
- [Deployment failure and rollback](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Pod lifecycle and restarts](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Resource management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Debug Services](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/)
- [Debug DNS](https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/)
- [Persistent volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Horizontal autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [API concurrency and conditional changes](https://kubernetes.io/docs/reference/using-api/api-concepts/)
