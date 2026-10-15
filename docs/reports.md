# Readable evidence and handover drafts

`report` turns an existing toolkit JSON file into a standalone HTML file, Markdown or an allowlisted summary JSON. It does not contact Kubernetes, load adjacent logs, start a server, open your browser or upload anything.

```bash
devops-toolkit report private-reports/diagnosis.json --output private-reports/diagnosis.html
devops-toolkit report private-reports/diagnosis.json --format markdown --output private-reports/diagnosis.md
devops-toolkit report private-reports/diagnosis.json --format json --output private-reports/summary.json
devops-toolkit handover private-reports/diagnosis.json --output private-reports/handover.md
```

Supported schema-1 inputs: diagnosis, release-check, offline manifest check, preflight, incident snapshots, workload bundle `report.json`, compare, timeline, drift, repair dry-run and doctor. It does not render arbitrary JSON, raw Kubernetes objects, policy files or repair JSONL directly. For repair history, first build a scoped JSON [timeline](timeline.md).

The output shows selected evidence, decisions, next steps, incomplete data and limitations. Snapshot views include pod readiness/restarts and Deployment replica counts. Comparison and timeline views include descriptions of observed changes and recognized repair audit outcomes; before/after raw values and images are excluded. No inferred root cause, fabricated impact or automatic declaration of resolution is added. Empty findings do not mean healthy.

HTML is static and self-contained: escaped text, no scripts or external assets, with a restrictive content security policy. Inputs are capped at 8 MiB; views display at most 500 rows, and strings are length-limited. Exports retain internal names. Secret redaction is best effort; arbitrary specs, logs and comparison values are excluded. Review the private file before sharing it.

Handover drafts deliberately leave owner, user impact and next-update time for an engineer to complete. They do not send to Slack, Teams, email or a ticketing service. Existing [alerts](alerts.md) are separate, explicitly configured outcome notifications.

## Existing CI integrations

`diagnose`, `release-check` and `manifest-check` accept `--format text` for readable terminal output while `--output` preserves their original JSON schema. JSON remains the stdout default for existing consumers; existing exit codes are unchanged.

The [automatic offline CI workflow](ci-integration.md) continues to publish only its fixed offline configuration report and summary. It is supplied with the new usability regression cases for future runs. No live evidence is automatically uploaded. You may use summary Markdown/JSON in your own trusted Jenkins or GitHub workflow after reviewing its contents and permissions. No new webhook, bot comment, external ticket or upload is enabled by an export.

Tests and runtime rendering have not been executed for this revision. Syntax inspection is not a usability or security test.
