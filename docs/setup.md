# Setup and release

## Local environment

Use Docker Compose or CPython 3.12 on Linux amd64. Other architectures need a regenerated dependency lock and a compatible image build. Run `make install` inside a virtual environment, then `make run`.

## CI configuration

Create a SonarQube Server project with key `devops-platform` and an HTTPS URL reachable from the runner. Configure its quality gate, including the required new-code coverage and issue thresholds.

Set:
- Actions secrets: `SONAR_TOKEN`, `SNYK_TOKEN`.
- Actions variable: `SONAR_HOST_URL`.
- GitHub environment `production`: required reviewers, main-only branches and no self-approval where available.
- Main branch rules: reviewed changes, no force push and required checks after automatic CI has been enabled.

Environment protections and branch rules must be configured in GitHub settings. Without them, the code cannot provide independent approval.

Open Actions → CI → Run workflow. Leave `publish` false for source/image checks. Set it true on main for a release candidate. Nothing runs automatically on a commit at present.

The release run executes both external gates against the same source SHA and image archive used by the publisher. It then publishes, signs and attests the digest. If signing fails after a push, the image may exist in GHCR but is not an approved release. Do not promote it.

Artifacts:
- `source-reports`: coverage and rendered manifests.
- `security-reports`: Trivy output, SBOM and archive identity.
- `candidate-image`: short-lived image archive.
- `release-evidence`: published digest, image identity, SBOM and reports.

The first GHCR package can be private even for a public repository. Make it public or supply a namespace-local image pull secret through `imagePullSecrets`.

## Verify a release

Obtain the full digest reference from `release-evidence/reports/release-image.txt` (the downloaded artifact may omit the outer reports folder). Verify the signature and SBOM attestation with a trusted Cosign installation:

```bash
cosign verify --certificate-identity https://github.com/Vishnu063/devops_platform/.github/workflows/ci.yml@refs/heads/main --certificate-oidc-issuer https://token.actions.githubusercontent.com YOUR_IMAGE_AT_DIGEST
cosign verify-attestation --type cyclonedx --certificate-identity https://github.com/Vishnu063/devops_platform/.github/workflows/ci.yml@refs/heads/main --certificate-oidc-issuer https://token.actions.githubusercontent.com YOUR_IMAGE_AT_DIGEST
```

Review the workflow result, source SHA and vulnerability reports as well. A signature identifies the workflow that signed the image; it does not independently establish that its code was trustworthy.

## Direct Helm deployment

Use a separate lab namespace and an approved image digest:

```bash
kubectl apply -f gitops/namespace.yaml
helm upgrade --install platform charts/platform --namespace platform --set image.digest=YOUR_SHA256_DIGEST --atomic --timeout 180s
kubectl -n platform rollout status deployment/platform
kubectl -n platform port-forward service/platform 8080:80
```

The digest value includes the `sha256:` prefix, without the repository. Do not manage the same release with both Helm CLI and Argo CD. Remove the direct Helm release before handing ownership to Argo.

For the stricter profile add `-f charts/platform/values-production.yaml` before `--set image.digest=...`. The cluster must have three eligible nodes in at least two labeled zones and spare rollout capacity. HPA requires metrics-server; NetworkPolicy requires an enforcing CNI.

## Argo CD

Install a supported Argo CD release from its official documentation. Apply `gitops/namespace.yaml` and `gitops/project.yaml` as an administrator. The application project cannot create arbitrary cluster resources.

Update `gitops/release.yaml` through a reviewed PR with the approved image digest. Apply **one** application manifest:
- `gitops/application.yaml` for the lab.
- `gitops/application-production.yaml` for the multi-zone profile.

Inspect the diff and sync manually. Verify Healthy/Synced and inspect the actual running image digest. Roll back by reverting the release PR and syncing the prior approved digest.

## Network and TLS

Default ingress allows only Prometheus pods with the expected label in namespace monitoring. Outbound connections from the API are denied. Match the policy selectors to the real monitoring deployment.

Public ingress is disabled. To enable it, configure the chart's `ingress` values: a supported controller class, hostname, existing TLS secret, controller namespace and pod labels. Only GET/HEAD root identity is intended for public use; the Ingress route exposes the exact root path. Enforce HTTPS redirects, rate limits and any required authentication at the chosen controller or gateway. Those controller-specific settings are not supplied.

## Monitoring

Install kube-prometheus-stack as release `monitoring` in namespace `monitoring`. Ensure its namespace and label selectors discover ServiceMonitor and PrometheusRule resources in platform. Apply `monitoring/service-monitor.yaml`.

Import the dashboard JSON and select the Prometheus data source. Confirm target discovery, request counters and latency under traffic. Configure Alertmanager receivers privately. Rules without a receiver do not deliver notifications. Default thresholds are starting points, not measured SLOs.

## Optional AWS lab

Authenticate locally using your AWS profile. Inspect account pricing before apply. The supplied Terraform creates only one isolated EC2 lab node and its network.

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Set your public key and current public IPv4 /32 in the local file.
terraform init
terraform fmt
terraform validate
terraform plan -out=lab.tfplan
terraform apply lab.tfplan
```

After initialization review and commit `.terraform.lock.hcl` for the target platforms. It is not supplied because provider initialization has not been run. The AMI lookup uses the current matching Ubuntu image; pin an approved AMI before relying on reproducible infrastructure.

For shared state, provision an encrypted, versioned, private S3 bucket separately, copy `infra/backend.tf.example` to `infra/backend.tf`, replace its values, and migrate with `terraform init -migrate-state`. Restrict state and .tflock object permissions. Back up state before migration.

Install Ansible on the control machine. Copy the inventory example to `ansible/inventory.local`, replace the address/key and verify the SSH host fingerprint. Then run:

```bash
ansible-playbook -i ansible/inventory.local ansible/k3s.yml
```

The playbook verifies the binary checksum and pins the installer source/hash. Recheck the selected k3s release's support and compatibility before deploying. It is a lab installer, not a multi-node cluster lifecycle tool. Use SSH and local forwarding for administration; the security group does not expose the Kubernetes API publicly.

Destroy the lab after use with `terraform destroy` from infra. Keep the state until destruction completes.

## Jenkins

Use a dedicated trusted main-only multibranch job, a Linux amd64 Docker agent labeled docker, Bash, Git and a full-history checkout. Configure Jenkins SCM trust/discovery settings to exclude untrusted branches and forks; an in-file branch check cannot protect against a malicious Jenkinsfile.

Set credentials `sonar-token` and `snyk-token`, plus environment `SONAR_HOST_URL`. Jenkins invokes the same three ci scripts, archives reports, and cleans the workspace. Publication remains in GitHub Actions so it cannot bypass the release signing and approval path.
