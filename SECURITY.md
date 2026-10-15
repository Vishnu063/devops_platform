# Reporting a security problem

Do not put credentials, kubeconfig, webhook URLs, Secret data, private policy contents or customer logs in public issues.

Use the repository's **Security → Report a vulnerability** option if private vulnerability reporting is enabled. If it is unavailable, open a public issue requesting a private reporting channel without vulnerability details or secrets; wait for the owner to provide one. No dedicated security inbox or response-time guarantee is established here.

Disable affected automation and preserve its private audit when an outcome is uncertain. A notification failure does not undo a Kubernetes mutation. See [operations controls](docs/operations.md) for pause and credential-revocation guidance.

This development version has not been production-validated. No supported release series or verified Kubernetes matrix has been published yet.
