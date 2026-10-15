# Receive an outcome notification

Notifications are optional and disabled by default. Supported payload formats are Slack incoming-webhook text, Teams Adaptive Card webhook and a generic JSON HTTPS webhook. You supply and approve the destination. No endpoint, channel, account or receiver is created by the toolkit.

## Configure the receiver

Copy [examples/alerts.json](../examples/alerts.json) to your private configuration and set `provider` to `slack`, `teams` or `webhook`. `url_env` names the environment variable that holds the receiver URL. The URL itself does not belong in the JSON or in Git.

Provide `DEVOPS_ALERT_WEBHOOK` through your trusted local secret manager/process environment. Do not paste a real webhook into shared shell history or commit it. The URL must be HTTPS, without userinfo or a fragment. Teams workflows must accept the documented Adaptive Card envelope; tenant authentication requirements may require an organization-managed relay. Arbitrary bearer-token/OAuth headers are not implemented.

## Opt in on one command

```bash
devops-toolkit watch-recovery --policy reports/recovery-policy.local.json \
  --execute --audit reports/recovery-UNIQUE-ID.jsonl \
  --notify-config alerts.local.json
```

The same flag works with `recover`, `repair`, `diagnose` and `release-check`. Invalid notification configuration prevents the operation from starting. Configuration validation does not test delivery. No notification is sent for other commands or unless the flag is supplied.

Only a fixed outcome record is sent: random event ID, timestamp, tool name, command, result label and exit code. It excludes context/namespace, resource identity, UIDs, policy details, reports, logs, stdout and webhook URLs. The event ID is also printed to the local command stderr so the receiver message can be correlated with that runner output. No report is automatically uploaded.

`recovery_succeeded` requires an exit-0 execution and the readiness-confirmed audit event. A successful preview is labeled separately. Failures/timeouts request attention; successful completion without a repair is not advertised as a repaired incident. Kubernetes readiness is not proof of end-user recovery.

## Delivery behavior

One HTTP POST, ten-second timeout, verified TLS, no redirects and no retries. A non-2xx response is a delivery failure. A 2xx response confirms HTTP acceptance, not that a human received or read the message. No mutation is retried because a notification failed. If the operation succeeded but notification failed, exit code is `3`; otherwise preserve the original nonzero operation code. Inspect the report/audit for the actual operational outcome.

This is a completion notification, not a durable alert queue or heartbeat. Host/process failure, a hard kill, invalid CLI syntax or an unavailable network can prevent notification. Use your independent monitoring for process health and stopped automation. Endpoint delivery, tenant compatibility and receiver configuration remain unverified.

Official payload references: [Slack incoming webhooks](https://api.slack.com/messaging/webhooks), [Teams webhook/Adaptive Cards](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook). No real notification has been sent during implementation.
