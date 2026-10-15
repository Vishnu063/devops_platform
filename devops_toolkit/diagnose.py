"""Read-only symptom detection. Findings are evidence, not proven root causes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ADVICE = {
    "CrashLoopBackOff": "Inspect previous container logs, exit code, dependencies and startup configuration.",
    "ImagePullBackOff": "Check image existence, registry reachability and pull credentials; use an approved digest.",
    "ErrImagePull": "Check image existence, registry reachability and pull credentials.",
    "OOMKilled": "Compare memory use with limits and node pressure; investigate leaks before adjusting limits.",
    "CreateContainerConfigError": "Check referenced ConfigMaps, Secrets and keys without exposing their values.",
    "CreateContainerError": "Inspect runtime, mounts and security settings; do not disable security controls blindly.",
    "RunContainerError": "Inspect entrypoint, permissions and container runtime events.",
    "Error": "Inspect termination exit code and previous logs; the reason alone does not identify the cause.",
    "Evicted": "Investigate node pressure and workload resource requests before recreating workloads.",
    "FailedScheduling": "Check requests, quotas, taints, affinity and PVC binding; do not remove constraints blindly.",
    "FailedMount": "Check volume references, CSI driver and storage permissions; do not delete PVCs.",
    "FailedAttachVolume": "Check CSI attachment state and node health; avoid forcing attachment of active volumes.",
    "Unhealthy": "Check probe path, port, timing and application dependencies; do not simply disable probes.",
    "BackOff": "Inspect container status to distinguish startup crashes from image-pull failures.",
    "FailedCreate": "Check admission, quota and controller permissions.",
    "FailedGetResourceMetric": "Check metrics API availability and container resource requests.",
    "FailedComputeMetricsReplicas": "Inspect HPA metrics and requests; avoid manual replica changes that fight HPA.",
}


def findings_for(resource, items):
    findings = []
    def add(name, signal, action):
        findings.append({"resource": resource + "/" + name, "signal": signal, "next_action": action})
    for item in items:
        name = item.get("metadata", {}).get("name", "unknown")
        status = item.get("status", {})
        if resource == "pods":
            if status.get("phase") == "Pending":
                add(name, "Pending", ADVICE["FailedScheduling"])
            if status.get("reason") == "Evicted":
                add(name, "Evicted", ADVICE["Evicted"])
            for c in status.get("containerStatuses", []) + status.get("initContainerStatuses", []):
                for key in ("state", "lastState"):
                    for state in c.get(key, {}).values():
                        reason = state.get("reason")
                        if reason in ADVICE:
                            add(name, c.get("name", "unknown") + ":" + key + ":" + reason, ADVICE[reason])
            for c in status.get("conditions", []):
                if c.get("type") == "Ready" and c.get("status") == "False" and status.get("phase") == "Running":
                    add(name, "NotReady", "Inspect readiness probes, readiness gates and application dependencies.")
        elif resource == "deployments":
            for c in status.get("conditions", []):
                if c.get("reason") == "ProgressDeadlineExceeded" and c.get("status") == "False":
                    add(name, "ProgressDeadlineExceeded", "Inspect failed rollout. Approved image-only recovery is available via recover; GitOps workloads need a source change.")
        elif resource == "events" and item.get("type") == "Warning":
            reason = item.get("reason", "UnknownWarning")
            add(name, reason, ADVICE.get(reason, "Inspect the event locally and consult the Kubernetes problem guide. Event messages are excluded from this report."))
        elif resource == "persistentvolumeclaims" and status.get("phase") != "Bound":
            add(name, "PVC:" + str(status.get("phase", "Unknown")), "Check StorageClass, provisioner, capacity and binding mode; pending can be expected with WaitForFirstConsumer.")
        elif resource == "horizontalpodautoscalers":
            for c in status.get("conditions", []):
                if (c.get("type") in {"AbleToScale", "ScalingActive"} and c.get("status") == "False") or (c.get("type") == "ScalingLimited" and c.get("status") == "True"):
                    add(name, c["type"], "Inspect HPA metrics, requests and min/max bounds; a scaling limit may be intentional.")
        elif resource == "jobs":
            if any(c.get("type") == "Failed" and c.get("status") == "True" for c in status.get("conditions", [])):
                add(name, "JobFailed", "Inspect exit status and backoff limit. Retry only if duplicate execution is safe.")
        elif resource == "nodes":
            for c in status.get("conditions", []):
                if (c.get("type") == "Ready" and c.get("status") != "True") or (c.get("type") in {"DiskPressure", "MemoryPressure", "PIDPressure", "NetworkUnavailable"} and c.get("status") == "True"):
                    add(name, c["type"] + ":" + c.get("status", "Unknown"), "Inspect node, runtime and infrastructure health. Draining or replacing requires capacity and workload review.")
    return findings


def main(argv=None):
    from .cli import Kube, QueryError, write_private
    import re
    parser = argparse.ArgumentParser(prog="python -m devops_toolkit diagnose")
    parser.add_argument("--context", required=True)
    parser.add_argument("--namespace", default="platform")
    parser.add_argument("--include-nodes", action="store_true", help="Optional cluster-wide node read")
    parser.add_argument("--output", help="New private JSON file")
    args = parser.parse_args(argv)
    if not args.context.strip() or args.context.startswith("-") or not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", args.namespace):
        parser.error("Use an explicit context and valid namespace")
    kube = Kube(args.context, args.namespace)
    report = {"schema_version": 1, "kind": "diagnosis", "context": args.context,
              "namespace": args.namespace, "created_at": datetime.now(timezone.utc).isoformat(),
              "findings": [], "unavailable": [], "observed_counts": {},
              "limitations": ["Symptoms do not prove root cause; old events and lastState may describe past failures.",
                              "DNS, traffic, TLS, RBAC, security, GitOps and control-plane health require separate checks.",
                              "No findings is not a cluster health guarantee. No repairs are performed."]}
    resources = ["pods", "deployments", "events", "persistentvolumeclaims", "horizontalpodautoscalers", "jobs"]
    if args.include_nodes:
        resources.append("nodes")
    for resource in resources:
        try:
            items = kube.get(resource)["items"]
            report["observed_counts"][resource] = len(items)
            report["findings"].extend(findings_for(resource, items))
        except (QueryError, KeyError, TypeError, AttributeError):
            report["unavailable"].append(resource)
    try:
        if args.output:
            write_private(Path(args.output), json.dumps(report, indent=2) + "\n")
    except OSError:
        print("Cannot save report: use a new output file with an existing parent directory.", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 2 if report["unavailable"] else 1 if report["findings"] else 0
