# Explain configuration drift without changing the cluster

Compare desired configuration from a reviewed Git checkout with the live Deployment/Service:

```bash
devops-toolkit drift --context YOUR_CONTEXT --namespace platform \
  --file k8s/release.yaml --output reports/drift.json
```

The same local `--chart`, `--release`, `--values` and `--set` options are supported. See [manifest input](manifest-input.md). The command does not clone Git, choose a revision, reconcile a controller, apply a patch or delete anything. You select and review the source checkout.

The report identifies the resource and changed JSON field paths, for example `/spec/replicas` or `/spec/template/spec/containers/0/image`. It omits before/after values, which might contain sensitive configuration. Names and paths can still be sensitive, so keep the report private.

## Comparison scope

- Supports apps/v1 Deployments and core/v1 Services in one explicit namespace.
- Compares desired spec fields and explicitly supplied metadata labels.
- Ignores status, annotations, generated metadata and live fields unspecified by desired input.
- Compares lists by position/shape. Reordering, injected sidecars, default representations, numeric/string differences and quantity syntax can create noise.
- Does not identify desired deletions, Secret/ConfigMap drift, ownership conflicts or every field managed by GitOps.
- Caps reported changes at 500 per resource and marks truncation.
- Missing/forbidden/unreachable live targets are unavailable, not proof that a resource is absent.

Unspecified and defaulted fields are handled conservatively; this is not a full server-side apply diff. A zero-drift result applies only to compared fields. Unsupported objects are listed and make the overall result incomplete rather than silently receiving a pass.

Exit codes: `0` no drift in supported compared fields; `1` observed drift; `2` unavailable/unsupported/truncated evidence or input/output failure. No auto-fix runs from a drift report. Let the owning Argo CD/Flux controller reconcile reviewed Git, or create a separately approved repair policy within the existing rules.

Implementation and mocked cases are included; no live drift check was run in this revision.
