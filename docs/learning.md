# Project walkthrough

Follow the release path in this order. At each stage, run the commands, inspect the output and keep notes on failures and fixes.

| Stage | Topics | Practical exercise |
| --- | --- | --- |
| 1. App and Git | Flask, Gunicorn, HTTP, health/readiness, logs, branch/PR/revert | Explain one request and one reviewed change |
| 2. Docker | Layers, build context, UID, health check | Build, inspect, run, stop and troubleshoot |
| 3. CI | Jobs, dependencies, permissions, artifacts | Explain why scan failure prevents publication |
| 4. Security | Secret scanning, SAST, CVEs, coverage gate, SBOM | Show an actual report and remediate a finding |
| 5. Kubernetes | Deployment, Service, probes, limits, PDB | Explain rolling update and diagnose bad release |
| 6. Helm/GitOps | Values, templates, desired state, reconciliation | Release a SHA and revert it through Git |
| 7. Monitoring | Scrapes, PromQL, alert duration, dashboards | Show target down and recovery |
| 8. Terraform | Plan/state/provider/network/SSH/IMDS | Explain plan, apply, drift and destroy |
| 9. Ansible | Inventory, privilege escalation, idempotence | Explain why rerunning does not reinstall k3s |
| 10. Incident response | Symptoms, evidence, cause, recovery | Present one real lab incident with timestamps |

## Review questions

1. What problem does this pipeline solve and why use one small service?
2. What is the difference between readiness and liveness in this service?
3. What runs in check-only mode, and which additional gates are required to publish?
4. Why is a public repository not enough to guarantee a public GHCR image?
5. Why are two replicas on one node insufficient for high availability?
6. What happens if the new pod never becomes ready?
7. How do you correlate a running digest with its source commit, signature and scan evidence?
8. Why revert Git rather than making a permanent imperative change in Argo?
9. What does Terraform state contain, and how would a team protect it?
10. What are the current limitations and what did you actually verify?

Keep a short record of completed exercises: the commit used, commands run, observed result and any fixes. Use those records when explaining the project.
