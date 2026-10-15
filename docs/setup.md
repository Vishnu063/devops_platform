# Setup and release

## 1. GitHub CI

Open Actions, select CI, select Run workflow on main. It tests and validates before publishing a commit-SHA image to GHCR. No cloud credentials are used.

After you want automatic runs, replace the CI trigger with push on main, pull_request and workflow_dispatch. Configure a main branch ruleset requiring the CI jobs, a reviewed PR, and no force pushes. Enable automatic CI before making these checks required, or PRs will wait indefinitely for checks. Repository code cannot enforce these settings itself.

## 2. SonarQube and Snyk

Create SonarQube project key `devops-platform` on a server reachable from the runner. Set repository variable `SONAR_HOST_URL` and Actions secret `SONAR_TOKEN`. Configure a quality gate (for example 80% new-code coverage and no new critical issues). The scanner waits for its result.

Set Actions secret `SNYK_TOKEN` from your Snyk account. Run External quality gates on the same main commit you intend to release. Missing credentials fail explicitly. This integration is not wired as a required standard-CI dependency; enforce its successful result during review. A SonarQube Cloud account additionally needs organization configuration; this supplied config targets Server/Community Build.

## 3. Local Kubernetes first

Use an existing local Kubernetes cluster with Helm 3. Build and publish through CI, make the GHCR package public, then:

```bash
helm upgrade --install platform charts/platform --namespace platform --create-namespace --set image.tag=YOUR_SUCCESSFUL_FULL_COMMIT_SHA --atomic --timeout 120s
kubectl -n platform rollout status deployment/platform
kubectl -n platform port-forward service/platform 8080:80
```

Open localhost:8080. Do not mix direct Helm releases and Argo ownership in the same namespace. Use the direct Helm route first, remove it with `helm uninstall platform -n platform`, then switch to GitOps.

## 4. Argo CD

Install Argo CD using its official installation guide. Set the successful SHA in gitops/release.yaml via reviewed PR. Apply gitops/application.yaml to the cluster hosting Argo CD. In Argo CD inspect the diff, sync manually, and wait for Healthy/Synced. This sample uses the default Argo project for one trusted lab; production needs a restricted AppProject.

Rollback: revert the release PR to the previous successful image SHA, merge, then sync. This restores Git as the source of truth.

## 5. Monitoring

Install the community kube-prometheus-stack Helm chart as release `monitoring` in namespace `monitoring`. Its default stack can exceed a small EC2 instance; run it locally or size explicitly. Ensure its ServiceMonitor and PrometheusRule namespace selectors include `platform` and its label selectors accept `release: monitoring`.

Apply monitoring/service-monitor.yaml after platform namespace exists. Confirm the Prometheus target is UP. Import monitoring/grafana-dashboard.json and select your Prometheus data source. The alert rule needs Alertmanager receiver configuration for notifications; none is supplied because contact credentials are private. Stdout logs are available through kubectl; no unused ELK/Loki stack is included.

## 6. Optional AWS lab

Terraform only creates a VPC, subnet, route, security group, SSH key and encrypted EC2 instance. Authenticate locally with your AWS profile. No AWS credentials belong in Git.

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Replace public_key and admin_cidr in your local file before proceeding.
terraform init
terraform fmt
terraform validate
terraform plan -out=lab.tfplan
terraform apply lab.tfplan
```

Inspect costs and the plan before apply. Copy ansible/inventory.example locally, replace IP and key path. Connect once with SSH and verify the host fingerprint. Run:

```bash
ansible-playbook -i ansible/inventory.local ansible/k3s.yml
```

Install Ansible on your control machine first. k3s version is explicit; check compatibility/security support before provisioning. The basic node is small and is not sized for SonarQube plus monitoring. API access is via SSH and localhost forwarding; port 6443 is not publicly exposed. Run kubectl on the node with sudo, or use an SSH tunnel and a securely copied kubeconfig.

Cleanup after the lab:

```bash
cd infra
terraform destroy
```

Keep state locally for a single operator. For teamwork migrate to an encrypted S3 backend with state locking and scoped access; that backend is intentionally not auto-provisioned.

## 7. Jenkins alternative

Use a trusted Linux agent labeled docker with Docker and Git. Configure a multibranch pipeline pointing to Jenkinsfile. Jenkins needs credentials IDs sonar-token (secret text), snyk-token (secret text), ghcr (username/password with a packages-write token), and environment SONAR_HOST_URL.

Use only trusted branches: Docker socket access grants host-level power, and untrusted PR code must not run alongside credentials. Jenkins does not include Terraform/Helm validation from GitHub CI; run those separately before release if choosing Jenkins alone.

## Additional deployment safeguards

See [readiness](readiness.md) for digest releases and network-policy selectors. The monitoring namespace/pod labels must match the real deployment; all other pod ingress and all API egress are denied by default. Public ingress remains disabled. The CNI must enforce these policies. No validation was performed during repository creation or hardening.
