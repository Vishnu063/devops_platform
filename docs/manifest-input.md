# Read YAML, JSON or a local Helm chart

`preflight`, `release-check`, `manifest-check` and `drift` share the same input loader. No manual JSON conversion is needed.

## Install optional YAML support later

From the repository in a Python 3.12+ virtual environment:

```bash
python -m pip install '.[yaml]'
```

The base CLI and JSON input use the standard library. YAML and Helm-rendered YAML use the optional pinned PyYAML dependency. Installing/building has not been performed during this revision. Nothing is published to PyPI.

## Existing manifests

```bash
devops-toolkit release-check --context YOUR_CONTEXT --namespace platform \
  --deployment YOUR_DEPLOYMENT --service YOUR_SERVICE --file k8s/release.yaml \
  --output reports/release-check.json
```

`--file` accepts one Kubernetes object, a Kubernetes List, or multiple YAML documents. Empty documents are ignored. JSON remains supported. Select the Deployment/Service explicitly when the input contains several applications.

The parser uses a safe loader, refuses duplicate keys/identities and YAML aliases, limits size/complexity, and rejects Python-specific tags/special types. Expand YAML anchors/aliases and quote date-like scalar values. A maximum 8 MiB and 2,000 objects are accepted; complexity limits are enforced during parsing/normalization. Helm output size is checked after bounded-time capture, so trusted charts are required. This parser is not full Kubernetes schema or admission validation.

## Local Helm rendering

```bash
devops-toolkit release-check --context YOUR_CONTEXT --namespace platform \
  --deployment YOUR_DEPLOYMENT --service YOUR_SERVICE \
  --chart ./charts/my-app --release my-app --values ./values/staging.yaml \
  --set image.digest=sha256:REPLACE_WITH_APPROVED_DIGEST \
  --output reports/release-check.json
```

Use one source: `--file` or `--chart`. Repeat `--values` and `--set` when needed. Never put real secrets in command-line settings or shared values files. `--release` defaults to platform; namespace comes from the command's explicit namespace.

`--chart` must be a trusted local directory containing Chart.yaml. The tool invokes `helm template` with argument arrays, an empty plugin directory and a bounded timeout. It does not accept remote charts, install/upgrade releases, run hooks, use a post-renderer, fetch dependencies or request server-side Helm rendering. Pre-vendor reviewed dependencies. Render errors are reported generically rather than echoing potentially sensitive values. Helm must already be installed on PATH.

A chart is rendered once per command and cached for its checks, so random template functions cannot silently produce two different candidates during one release check. Helm capability/default behavior still depends on the installed Helm version; record versions with your evidence. Chart hooks may be rendered as object definitions but are not executed.

For fully offline configuration checks, use `manifest-check` with the same source flags. It never creates a Kubernetes client. For live objects/references/capacity, use `release-check` with a trusted explicit context. [CI integration](ci-integration.md) keeps these two result types separate.
