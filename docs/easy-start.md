# Your first useful result

Start offline. You do not need AWS, a cluster or Docker for this walkthrough.
These are commands for you to run later; this revision has not been executed or usability-tested.

## 1. Install from this repository

Use Python 3.12 or later in a virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install '.[yaml]'
devops-toolkit doctor
```

`doctor` explains local prerequisites. It does not run Docker/Helm, inspect credentials or contact a cluster by default. `--profile cluster`, `release`, `helm` or `demo` checks that task's executables are on PATH. A PASS means those limited checks passed; it does not prove they work or that a workload is healthy.

## 2. Explore an example without a cluster

```bash
mkdir -m 700 private-reports
devops-toolkit example --scenario crash --output private-reports/example.json
devops-toolkit report private-reports/example.json --output private-reports/example.html
```

Open `private-reports/example.html` in your browser. It is a standalone file with no scripts, remote assets or telemetry. It shows an illustrative symptom, suggested investigation and limits. The example is fabricated and clearly labeled; no Kubernetes command runs.

Also available: `--scenario image` and `--scenario selector`. A selector example illustrates manual investigation; it is not proof that live diagnosis detects every selector problem.

## 3. Get the command for your task

```bash
devops-toolkit guide
```

Choose a task and answer short prompts. The guide prints a POSIX-shell command for you to review and copy. It never executes that command. It does not generate repair execution commands. Use command `--help` in scripts/noninteractive terminals. Windows users should adapt shell quoting and activation to their shell.

## 4. Diagnose your application when ready

These commands contact the explicitly selected cluster. Use an existing context and a namespace you are authorized to read. No context is switched and no repair runs.

```bash
devops-toolkit doctor --profile cluster --context YOUR_CONTEXT --namespace platform
devops-toolkit diagnose --context YOUR_CONTEXT --namespace platform \
  --format text --output private-reports/diagnosis.json
devops-toolkit report private-reports/diagnosis.json \
  --output private-reports/diagnosis.html
```

Optional doctor access checks query `kubectl auth can-i list` for common diagnosis/bundle resources. They do not grant access, check every command's permissions, read Secret values or verify repair rights. Missing tools/access need your normal installation/RBAC process; nothing is auto-installed or granted.

Diagnosis explains observed symptoms and next steps. Events and last states may be historical. No findings is not a health guarantee. Suggested `kubectl get ... -o wide` reads are printed only for validated pod/Deployment identities with explicit scope; they are never run automatically.

## 5. Prepare a handover

```bash
devops-toolkit handover private-reports/diagnosis.json \
  --output private-reports/handover.md
```

Fill in owner, impact and next update time. Review before copying into a ticket. The toolkit does not guess business impact, claim incident resolution or send the draft.

For a real before/after history, use [timeline](timeline.md) on same-scope snapshots and scoped repair audits, save its JSON with `--format json`, then export that JSON with `report` or `handover`. The export retains observed change descriptions and audit outcomes; raw comparison values are excluded. Readiness evidence is not a business-health check.

## Choose the next task

| Task | Command | What you need |
| --- | --- | --- |
| Check a local release file | `manifest-check --file release.yaml --format text` | Optional YAML extra; no cluster |
| Check live release risks | `release-check --context … --format text` | kubectl, scoped read access; Docker for image access |
| Collect one workload's evidence | `bundle --context … --deployment … --output …` | Read access to Deployment, ReplicaSets, Pods, Services and Events |
| Explain desired-versus-live fields | `drift --context … --file …` | Explicit context and read access |
| Validate an existing approved repair | `repair-dry-run --policy …` | Policy, live guards, patch authorization and admission |
| Propose a GitOps source change | `gitops-propose --before … --after … --path … --output …` | Original and reviewed plain Deployment manifests |

Use `devops-toolkit COMMAND --help` for complete arguments. Every output path must be new; export commands need an existing private parent. POSIX files use mode 0600 and new evidence/proposal directories use 0700; check equivalent protections on your operating system. Internal resource names remain visible. Redaction is best effort. Do not automatically upload live reports.

[Report/export details](reports.md) · [GitOps proposal guide](gitops-proposals.md) · [All commands](toolkit.md)

## If you get stuck

Run `devops-toolkit suggest --issue stuck`, or `devops-toolkit suggest --report private-reports/diagnosis.json` if you saved evidence. It explains possible causes, steps and verification without executing them. See [suggestions](suggestions.md) for supported issues and recovery boundaries.
