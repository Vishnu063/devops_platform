# Propose a GitOps image correction

When Argo CD or Flux owns a workload, repair its reviewed Git source. Direct recovery still refuses recognized GitOps ownership. `gitops-propose` helps prepare a local review bundle; it never edits the checkout, creates a commit/PR, applies a patch or triggers reconciliation.

1. Copy the original plain Deployment source manifest to a private candidate file.
2. Change only regular-container image lines to reviewed, compatible digest-pinned references.
3. Generate a proposal:

```bash
devops-toolkit gitops-propose \
  --before apps/api/deployment.yaml \
  --after private-reports/deployment-candidate.yaml \
  --path apps/api/deployment.yaml --namespace platform \
  --output private-reports/gitops-proposal
```

`--path` identifies the original repository-relative source file. It is a label in the review patch, not a file the toolkit writes. Omitted manifest namespaces use `--namespace`; explicit namespaces are retained in the review metadata. These are source objects, not proof of live identity or ownership.

The new private directory contains:

| File | Purpose |
| --- | --- |
| `change.patch` | Image-line-only unified diff with zero context |
| `proposal.json` | Target/container identities, required approval and limits |
| `REVIEW.md` | Source review, image verification, PR and reconciliation checklist |

Zero context prevents adjacent environment/configuration values being copied. Review it against the current source; do not blindly apply a zero-context patch. Old and proposed image references remain visible. Existing output directories are refused, and a write error can leave a partial private directory for inspection.

Supported: plain apps/v1 Deployment YAML/JSON files, including multiple Deployments, with isolated image lines. Original/candidate object identities, ordering of containers and all other parsed fields must match. All textual changes must be isolated image lines without comments; formatting-only/unrelated changes, comments on changed lines, container additions/removals and mutable candidate image tags are refused. Inputs are limited to 1 MiB each. YAML requires the optional YAML extra.

Helm values/templates, rendered charts, Kustomize overlays, init-container changes, Service selector changes, resource budgets and replica edits are outside this proposal command. Edit their actual source through your normal reviewed process. The toolkit cannot determine whether the supplied file is really the controller's source.

Before making your normal PR, verify the source branch and images: availability, signature, architecture, compatibility, data migrations and rollback constraints. After approval, use the owning controller's normal reconciliation flow and verify application health. A generated proposal is not an execution approval, policy or evidence of recovery.

No GitOps proposal or reconciliation has been executed for this revision.
