# Operations runbook

| Symptom | Investigate | Recovery |
| --- | --- | --- |
| ImagePullBackOff | kubectl describe pod; SHA exists; GHCR visibility | Fix release tag or local pull credentials |
| Readiness failure | kubectl logs; describe; port and route | Fix configuration or revert release PR |
| Rollout stuck | kubectl rollout status; events; CPU/memory | Inspect capacity, correct requests, or revert |
| Trivy/Snyk gate fails | Inspect CVE, fixed version, affected layer | Update base image and rebuild; do not silence gate |
| Gitleaks finds a real secret | Stop release; revoke exposed credential | Rotate first, then remove it and clean history with coordination |
| Sonar fails | Coverage path, token, host reachability, quality gate | Correct analysis/configuration or code |
| Prometheus target down | Service endpoints, monitor selectors, /metrics | Correct selector/network/release and wait for recovery |
| Node down | EC2 state, system journal, disk/memory | Restore node; single-node lab has no HA |

Useful commands:

```bash
kubectl -n platform get pods,svc,endpoints
kubectl -n platform describe deployment platform
kubectl -n platform logs deployment/platform --tail=100
kubectl -n platform get events --sort-by=.metadata.creationTimestamp
```

## Controlled incident exercises

1. In a separate practice branch change the image tag to a nonexistent SHA. Observe image pull events. Revert and recover. Do not merge broken tags into main.
2. Change readiness path in a practice release. Observe a stalled rollout and why maxUnavailable=0 preserves existing ready replicas when capacity permits.
3. Delete one pod. Observe replacement and request continuity. This does not demonstrate node-level HA.
4. Stop the app target and inspect the Prometheus alert after two minutes. Restore it and observe resolution.

Record actual timestamps, symptoms, cause, fix and evidence in a GitHub issue after each exercise. Do not fabricate availability, deployment-speed or incident metrics.
