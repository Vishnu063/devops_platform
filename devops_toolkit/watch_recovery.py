"""Bounded monitoring for one policy-approved rollout; never retries a repair."""
import argparse
import json
from pathlib import Path
import sys
import time

from .recovery import fingerprint, load_policy, plan, recovered


def failed_rollout(deployment):
    status = deployment.get("status", {})
    return (status.get("observedGeneration", 0) == deployment["metadata"]["generation"] and
            any(c.get("type") == "Progressing" and c.get("status") == "False" and
                c.get("reason") == "ProgressDeadlineExceeded" for c in status.get("conditions", [])))


def monitor(policy_path, execute=False, audit=None, interval=15, max_wait=900,
            recovery_timeout=180, failure_observations=3):
    from .cli import Kube
    from .recovery import main as recover_main
    policy = load_policy(policy_path)
    original_policy = fingerprint(policy)
    if execute:
        if not audit or Path(audit).exists() or not Path(audit).parent.is_dir():
            raise ValueError("Execution requires a new audit file and existing parent")
    kube = Kube(policy["context"], policy["namespace"])
    deadline, consecutive = time.monotonic() + max_wait, 0
    print("Monitoring one approved rollout; " + ("automatic recovery enabled." if execute else "preview only."), flush=True)
    while time.monotonic() < deadline:
        # Recheck expiry and reject a policy edit instead of silently changing authorization.
        if fingerprint(load_policy(policy_path)) != original_policy:
            raise ValueError("Policy changed while monitoring")
        deployment = kube.get("deployment", policy["deployment"])
        namespace = kube.get("namespace", policy["namespace"])
        # All scope, opt-in, GitOps, image, template and attempt-latch guards apply while waiting.
        _, changes = plan(deployment, namespace, policy, require_failure=False)
        if recovered(deployment, deployment):
            print("Rollout is ready; no repair needed.", flush=True)
            return 0
        consecutive = consecutive + 1 if failed_rollout(deployment) else 0
        print(json.dumps({"state": "failed" if consecutive else "waiting",
                          "consecutive_failure_observations": consecutive}), flush=True)
        if consecutive >= failure_observations:
            if not execute:
                print(json.dumps({"mode": "preview", "changes": changes}), flush=True)
                print("Approved failure detected. No mutation performed.", flush=True)
                return 0
            # Delegate once. recover re-reads live state/policy and makes a conditional patch.
            # Any timeout/error is returned to the operator, never retried by this monitor.
            return recover_main(["--policy", policy_path, "--execute", "--audit", audit,
                                 "--timeout", str(recovery_timeout)], expected_policy_sha256=original_policy)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval, remaining))
    print("Monitoring window ended without a repair. Review rollout state.", flush=True)
    return 1


def main(argv=None):
    from .cli import QueryError
    parser = argparse.ArgumentParser(prog="python -m devops_toolkit watch-recovery")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--execute", action="store_true", help="Enable automatic approved recovery; default is preview")
    parser.add_argument("--audit", help="Required with execute: new private JSONL audit path")
    parser.add_argument("--interval", type=int, choices=range(5, 61), default=15, metavar="5..60")
    parser.add_argument("--max-wait", type=int, choices=range(30, 3601), default=900, metavar="30..3600")
    parser.add_argument("--recovery-timeout", type=int, choices=range(30, 601), default=180, metavar="30..600")
    args = parser.parse_args(argv)
    try:
        return monitor(args.policy, args.execute, args.audit, args.interval,
                       args.max_wait, args.recovery_timeout)
    except (QueryError, OSError, ValueError, KeyError, TypeError, AttributeError):
        print("Monitor stopped: check approved policy, expiry, target eligibility and API access. "
              "If recovery started, inspect its audit and live state before retrying.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Monitor interrupted. If recovery started, inspect audit and live state before restarting.", file=sys.stderr)
        return 2
