# Validate an approved repair without saving the patch

A normal `recover`/`repair` preview calculates a proposed correction locally. `repair-dry-run` additionally asks Kubernetes to validate that exact JSON patch using **--dry-run=server**.

```bash
devops-toolkit repair-dry-run --policy reports/recovery-policy.local.json \
  --output reports/repair-dry-run.json
```

Use an existing reviewed image or general repair policy. [Generate one](policies.md) from the exact live state first. The command checks identity, spec/template hash, expiry, opt-in, ownership, namespace pause and replica/HPA rules, then submits one server dry-run request. It never switches to a real patch or retries a failed request.

The dry-run patch contains the same persistent-attempt annotation the real repair would set, but the server dry-run request does not persist that annotation or the spec. The returned spec and latch must match the planned correction; admission changes produce NEEDS_REVIEW. The report does not copy arbitrary patched field values or Secret data.

## What it proves

A SERVER_ACCEPTED result means Kubernetes accepted this dry-run request under its authorization/admission rules at that moment. Server dry-run requires the same patch permission as execution. Admission webhooks must support dry-run; refusal or network failure remains incomplete, not a pass.

It does not start a rollout, pull images, reserve resources, verify readiness or guarantee that a subsequent real patch will be accepted. UID/resourceVersion and all live guards are rechecked for real execution. A dry-run does not create a repair audit, clear a latch, approve the fix or authorize bypassing GitOps.

Image/container validation can run before a failed-rollout condition exists, provided the other exact-state guards pass. The report explicitly shows whether an observed failed rollout exists and whether real execution would require it. `recover`/`repair` retain their original failed-rollout rules.

Exit codes: `0` server accepted the expected spec/latch, `1` admission returned a changed result requiring review, `2` refused/incomplete/error. No persistent mutation is requested by this command. Kubernetes' [dry-run API behavior](https://kubernetes.io/docs/reference/using-api/api-concepts/) and [kubectl patch reference](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_patch/) define the server contract. Live validation remains unrun.

Defaulted API fields can make a correction differ from a hand-written approval even when it looks equivalent. Review the result and use a known compatible, fully specified baseline rather than weakening the equality guard or retrying execution blindly. No default normalization or admission bypass is performed.
