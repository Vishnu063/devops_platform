"""Policy-bound image recovery. No policy is enabled by default."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

from .controls import ensure_enabled

PREFIX = "devops-platform.io/"


def fingerprint(template):
    return hashlib.sha256(json.dumps(template, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_policy(path):
    raw = Path(path).read_bytes()
    if len(raw) > 65536:
        raise ValueError("Policy too large")
    p = json.loads(raw)
    required = {"context", "namespace", "namespace_uid", "deployment", "deployment_uid",
                "failed_template_sha256", "approved_images", "expires_at"}
    if not isinstance(p, dict) or set(p) != required:
        raise ValueError("Policy fields must match the documented schema")
    if any(not isinstance(p[k], str) or not p[k] for k in required - {"approved_images"}):
        raise ValueError("Policy identity fields must be nonempty strings")
    if not p["context"].strip() or p["context"].startswith("-"):
        raise ValueError("Invalid context")
    for k in ("namespace", "deployment"):
        if not re.fullmatch(r"[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?", p[k]):
            raise ValueError("Invalid resource name")
    if not re.fullmatch(r"[0-9a-f]{64}", p["failed_template_sha256"]):
        raise ValueError("Invalid template fingerprint")
    expiry = datetime.fromisoformat(p["expires_at"].replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError("Policy expired or timezone missing")
    images = p["approved_images"]
    if not isinstance(images, dict) or not images or any(
            not isinstance(k, str) or not isinstance(v, str) or
            not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", k) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./:_-]*@sha256:[0-9a-f]{64}", v)
            for k, v in images.items()):
        raise ValueError("Approved images require named containers and immutable digests")
    return p


def plan(deployment, namespace, p, *, require_failure=True):
    ensure_enabled(namespace, p["namespace_uid"])
    m, spec, status = deployment["metadata"], deployment["spec"], deployment.get("status", {})
    if namespace["metadata"]["uid"] != p["namespace_uid"] or m["uid"] != p["deployment_uid"]:
        raise ValueError("Resource identity changed")
    if m["name"] != p["deployment"] or m["namespace"] != p["namespace"]:
        raise ValueError("Resource scope mismatch")
    annotations, labels = m.get("annotations", {}), m.get("labels", {})
    if annotations.get(PREFIX + "allow-image-recovery") != "true":
        raise ValueError("Deployment has not opted into image recovery")
    if any(k.startswith(("argocd.argoproj.io/", "kustomize.toolkit.fluxcd.io/", "helm.toolkit.fluxcd.io/"))
           for k in list(annotations) + list(labels)) or labels.get("app.kubernetes.io/managed-by", "").lower() in {"argocd", "flux"}:
        raise ValueError("GitOps-managed workload: repair its source of truth")
    if m.get("deletionTimestamp") or spec.get("paused") or spec.get("replicas", 1) < 1:
        raise ValueError("Deleting, paused or scaled-to-zero Deployment")
    if require_failure and status.get("observedGeneration", 0) != m["generation"]:
        raise ValueError("Controller has not observed this generation")
    if require_failure and not any(c.get("type") == "Progressing" and c.get("status") == "False" and
               c.get("reason") == "ProgressDeadlineExceeded" for c in status.get("conditions", [])):
        raise ValueError("No observed failed rollout; automatic repair is not applicable")
    if fingerprint(spec["template"]) != p["failed_template_sha256"]:
        raise ValueError("Template differs from the approved failure")
    if annotations.get(PREFIX + "recovery-attempt"):
        raise ValueError("Recovery already attempted; operator review required before resetting latch")
    containers = spec["template"]["spec"]["containers"]
    if set(p["approved_images"]) != {c["name"] for c in containers}:
        raise ValueError("Approve all and only regular containers; init containers remain unchanged")
    patch = [{"op": "test", "path": "/metadata/uid", "value": m["uid"]},
             {"op": "test", "path": "/metadata/resourceVersion", "value": m["resourceVersion"]}]
    changes = []
    for i, c in enumerate(containers):
        target = p["approved_images"][c["name"]]
        if target != c["image"]:
            patch.append({"op": "replace", "path": f"/spec/template/spec/containers/{i}/image", "value": target})
            changes.append({"container": c["name"], "before": c["image"], "after": target})
    if not changes:
        raise ValueError("Approved images already deployed; image recovery cannot address this failure")
    patch.append({"op": "add", "path": "/metadata/annotations/devops-platform.io~1recovery-attempt",
                  "value": p["failed_template_sha256"]})
    return patch, changes


def audit_write(stream, event, **values):
    stream.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "event": event, **values}) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def recovered(current, applied):
    if current["metadata"]["uid"] != applied["metadata"]["uid"] or current["spec"] != applied["spec"]:
        raise ValueError("Workload changed during recovery; stopped verification")
    status, desired = current.get("status", {}), current["spec"].get("replicas", 1)
    return (status.get("observedGeneration", 0) >= applied["metadata"]["generation"] and
            all(status.get(k, 0) == desired for k in ("replicas", "updatedReplicas", "readyReplicas", "availableReplicas")) and
            status.get("unavailableReplicas", 0) == 0)


def main(argv=None, *, expected_policy_sha256=None):
    from .cli import Kube, QueryError
    parser = argparse.ArgumentParser(prog="python -m devops_toolkit recover")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--execute", action="store_true", help="Apply approved recovery once; default is preview")
    parser.add_argument("--audit", help="Required for execute: new private JSONL file, parent must exist")
    parser.add_argument("--timeout", type=int, default=180, choices=range(30, 601), metavar="30..600")
    args = parser.parse_args(argv)
    mutation_started = False
    try:
        p = load_policy(args.policy)
        if expected_policy_sha256 is not None and fingerprint(p) != expected_policy_sha256:
            raise ValueError("Policy changed before recovery")
        kube = Kube(p["context"], p["namespace"])
        deployment = kube.get("deployment", p["deployment"])
        namespace = kube.get("namespace", p["namespace"])
        patch, changes = plan(deployment, namespace, p)
        print(json.dumps({"mode": "execute" if args.execute else "preview", "deployment": p["deployment"], "changes": changes}))
        if not args.execute:
            return 0
        if not args.audit:
            raise ValueError("Execute requires a new audit path")
        fd = os.open(args.audit, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            audit_write(stream, "intent", context=p["context"], namespace=p["namespace"],
                        deployment=p["deployment"], uid=p["deployment_uid"], changes=changes,
                        policy_sha256=fingerprint(p))
            try:
                if datetime.fromisoformat(p["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                    raise ValueError("Policy expired before mutation")
                ensure_enabled(kube.get("namespace", p["namespace"]), p["namespace_uid"])
                mutation_started = True
                applied = json.loads(kube.run("patch", "deployment", p["deployment"], "--type=json",
                                              "-p", json.dumps(patch), "-o", "json"))
                audit_write(stream, "patch_acknowledged", generation=applied["metadata"]["generation"])
                actual_images = {c["name"]: c["image"] for c in applied["spec"]["template"]["spec"]["containers"]}
                if actual_images != p["approved_images"]:
                    raise ValueError("Admission changed the approved images")
                deadline, stable = time.monotonic() + args.timeout, 0
                while time.monotonic() < deadline:
                    current = kube.get("deployment", p["deployment"])
                    stable = stable + 1 if recovered(current, applied) else 0
                    if stable >= 3:
                        audit_write(stream, "deployment_ready", consecutive_observations=stable)
                        print("Deployment ready in three observations. Verify application health separately.")
                        return 0
                    time.sleep(5)
                audit_write(stream, "verification_timeout")
                print("Recovery submitted, but readiness was not confirmed. No second repair attempted.")
                return 1
            except (QueryError, OSError, ValueError, KeyError, TypeError):
                audit_write(stream, "outcome_unknown", note="Inspect live state; never retry blindly")
                raise
    except (QueryError, OSError, ValueError, KeyError, TypeError, AttributeError):
        # Do not echo kubectl output, file contents or credentials.
        print("Recovery stopped. " + ("A change may have occurred; inspect audit and live state."
              if mutation_started else "No mutation attempted; check policy, opt-in, identities and failed-rollout eligibility."), file=sys.stderr)
        return 2
