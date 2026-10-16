# Before calling this production-ready

Use this as a record of remaining work. Checking in a procedure does not mean it has been executed. Keep real receiver URLs, credentials and connected-cluster reports out of Git.

The existing local and disposable-cluster results are in [compatibility.md](compatibility.md). Add new evidence there with the source commit, environment, command, result and remaining limitations.

## Protect main

In GitHub, open **Settings → Rules → Rulesets** and create an active branch ruleset targeting the default branch:

- Restrict deletion and block force pushes.
- Require a pull request before merging. For a solo maintainer, leave the required approval count at zero unless another reviewer is available.
- Require the exact check **Offline toolkit and manifest checks** after it has appeared on a passing PR.
- Require conversation resolution.
- Review bypass permissions; do not assume administrators are covered if a bypass is configured.

The toolkit workflow runs on every pull request and main push, including documentation-only changes, so path filters cannot leave this required check pending. Do not require the manual publication workflow on ordinary PRs.

Verify the rule with a disposable PR: the check must run, a failing check must prevent merge for a non-bypassing identity, and a passing check must allow the normal merge path. Inspect deletion/force-push rules in settings; do not attempt destructive changes to main as a test.

Repository administration access is needed to configure these rules. Changes to Markdown or workflow files do not activate them.

## Validate on a cloud test cluster

- [ ] Record the provider, Kubernetes/client versions and source commit.
- [ ] Use a disposable namespace and read-only identity for the initial checks.
- [ ] Run `doctor`, `release-check`, `diagnose` and `incident` against explicit targets.
- [ ] Exercise missing-image, missing-reference, selector and capacity cases; record both expected failures and successful checks.
- [ ] Inspect report redaction before sharing any evidence.
- [ ] Test a separately approved repair, refusal after state drift, readiness and application HTTP behavior.
- [ ] Confirm cleanup and document costs. Do not describe local kind evidence as cloud validation.

Use the [release-check guide](release-check.md), [repair guide](automatic-repair.md) and [operations guide](operations.md) for supported flags and boundaries.

## Confirm real alert delivery

- [ ] Choose an approved test receiver and use the private configuration described in [alerts.md](alerts.md).
- [ ] Run a non-mutating supported command with `--notify-config`.
- [ ] Match the event ID printed locally to the receiver's message.
- [ ] Check the payload contains no resource identities, logs or credentials.
- [ ] Record HTTP acceptance and observed message delivery separately.
- [ ] Exercise receiver failure against a controlled endpoint; check the operation outcome remains distinguishable from delivery failure.

No real receiver was contacted as part of this documentation change.

## Prove a release

- [ ] Configure the production environment's reviewer and branch restrictions in GitHub settings.
- [ ] Run source, image and external quality/security gates with authorized credentials.
- [ ] Confirm missing credentials or a failed gate prevents publication.
- [ ] Record the published digest, signature verification and SBOM attestation.
- [ ] Review the GitOps release change and sync to the test cluster.
- [ ] Check application traffic, graceful shutdown and rollback behavior; measure rather than assume acceptable thresholds.

Do not add credentials to PR jobs or enable publication just to make a badge green. See [setup](setup.md) and [readiness](readiness.md).

## Ask another engineer to try it

Use the tasks in [feedback.md](feedback.md). Record where setup failed, confusing output, time taken and the changes made afterward. Automated smoke checks are useful but do not replace this feedback.
