"""Compare selected incident fields offline. Never contacts Kubernetes."""
from datetime import datetime
import json
from pathlib import Path

MAX_SNAPSHOT = 8 * 1024 * 1024


def load_snapshot(path):
    with Path(path).open("rb") as handle:
        payload = handle.read(MAX_SNAPSHOT + 1)
    if len(payload) > MAX_SNAPSHOT:
        raise ValueError("Snapshot is too large")
    report = json.loads(payload)
    if not isinstance(report, dict) or type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise ValueError("Expected an incident snapshot with schema_version 1")
    for name in ("context", "namespace", "created_at"):
        if not isinstance(report.get(name), str) or not report[name]:
            raise ValueError("Missing snapshot identity")
    moment = datetime.fromisoformat(report["created_at"].replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("Snapshot timestamps need a timezone")
    for collection in ("pods", "deployments", "events"):
        records = report.get(collection)
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise ValueError("Expected an incident snapshot, not a preflight report")
    for collection in ("pods", "deployments"):
        names = []
        for item in report[collection]:
            if not isinstance(item.get("name"), str) or not item["name"]:
                raise ValueError("Missing resource name")
            names.append(item["name"])
            if not isinstance(item.get("images", []), list) or any(
                    not isinstance(image, str) for image in item.get("images", [])):
                raise ValueError("Invalid image list")
            if collection == "pods":
                for key in ("uid", "phase"):
                    if item.get(key) is not None and not isinstance(item[key], str):
                        raise ValueError("Invalid pod identity/state")
                containers = item.get("containers", [])
                if not isinstance(containers, list):
                    raise ValueError("Invalid container list")
                container_names = []
                for container in containers:
                    if not isinstance(container, dict) or not isinstance(container.get("name"), str):
                        raise ValueError("Invalid container identity")
                    if container.get("ready") is not None and type(container["ready"]) is not bool:
                        raise ValueError("Invalid container readiness")
                    if container.get("reason") is not None and not isinstance(container["reason"], str):
                        raise ValueError("Invalid container state")
                    container_names.append(container["name"])
                    restarts = container.get("restarts", 0)
                    if type(restarts) is not int or restarts < 0:
                        raise ValueError("Invalid restart count")
                if len(container_names) != len(set(container_names)):
                    raise ValueError("Duplicate container names")
            else:
                for key in ("desired", "ready", "updated"):
                    if type(item.get(key, 0)) is not int or item.get(key, 0) < 0:
                        raise ValueError("Invalid replica count")
        if len(names) != len(set(names)):
            raise ValueError("Duplicate resource names")
    for event in report["events"]:
        if event.get("uid") is not None and not isinstance(event["uid"], str):
            raise ValueError("Invalid event UID")
        for key in ("type", "reason", "object"):
            if event.get(key) is not None and not isinstance(event[key], str):
                raise ValueError("Invalid event identity")
        if event.get("count") is not None and (type(event["count"]) is not int or event["count"] < 0):
            raise ValueError("Invalid event count")
    return report, moment


def compare_files(before_path, after_path):
    before, start = load_snapshot(before_path)
    after, end = load_snapshot(after_path)
    if (before["context"], before["namespace"]) != (after["context"], after["namespace"]):
        raise ValueError("Snapshots must use the same context and namespace")
    if end < start:
        raise ValueError("After snapshot is older than before snapshot")
    findings, warnings = [], []

    def add(kind, resource, message, old=None, new=None):
        findings.append({"kind": kind, "resource": resource, "message": message,
                         "before": old, "after": new})

    for label, report in (("before", before), ("after", after)):
        if report.get("example"):
            warnings.append(label + " snapshot is illustrative sample data, not real incident evidence")
        if report.get("unavailable"):
            warnings.append(label + " collection was partial")
        if report.get("pods_truncated"):
            warnings.append(label + " pod list was truncated")
        if report.get("deployment_count", len(report["deployments"])) > len(report["deployments"]):
            warnings.append(label + " deployment list was truncated")
        if report.get("event_count", len(report["events"])) > len(report["events"]):
            warnings.append(label + " event list was truncated")
    warnings.append("Only captured fields are compared; missing records do not prove deletion.")
    warnings.append("Changes are evidence to investigate, not proof of the root cause.")

    for collection in ("deployments", "pods"):
        old_items = {item["name"]: item for item in before[collection]}
        new_items = {item["name"]: item for item in after[collection]}
        kind = "deployment" if collection == "deployments" else "pod"
        for name in sorted(old_items.keys() - new_items.keys()):
            add("not-captured", kind + "/" + name, "Not captured in the after snapshot")
        for name in sorted(new_items.keys() - old_items.keys()):
            add("first-captured", kind + "/" + name, "First captured in the after snapshot")
        for name in sorted(old_items.keys() & new_items.keys()):
            old, new = old_items[name], new_items[name]
            target = kind + "/" + name
            old_images, new_images = sorted(old.get("images", [])), sorted(new.get("images", []))
            if old_images != new_images:
                add("image-change", target, "Image references changed", old_images, new_images)
            if collection == "deployments":
                for key in ("ready", "desired", "updated"):
                    if old.get(key, 0) != new.get(key, 0):
                        add("replicas-change", target, key + " replicas changed",
                            old.get(key, 0), new.get(key, 0))
                continue
            if old.get("uid") and new.get("uid") and old["uid"] != new["uid"]:
                add("pod-replaced", target, "Pod UID changed; restart counters are not comparable")
                continue
            if not old.get("uid") or not new.get("uid"):
                warnings.append(target + " has legacy data without UID; counter continuity is uncertain")
            if old.get("phase") != new.get("phase"):
                add("phase-change", target, "Pod phase changed", old.get("phase"), new.get("phase"))
            old_containers = {c["name"]: c for c in old.get("containers", [])}
            new_containers = {c["name"]: c for c in new.get("containers", [])}
            for container in sorted(old_containers.keys() & new_containers.keys()):
                left, right = old_containers[container], new_containers[container]
                resource = target + "/" + container
                previous, current = left.get("restarts", 0), right.get("restarts", 0)
                if current > previous:
                    add("restarts-increased", resource, "Restart counter increased", previous, current)
                elif current < previous:
                    add("counter-reset", resource, "Restart counter decreased/reset; do not treat as recovery",
                        previous, current)
                for key in ("ready", "reason"):
                    if left.get(key) != right.get(key):
                        add("container-change", resource, key + " changed", left.get(key), right.get(key))

    def warning_events(report):
        result = {}
        for event in report["events"]:
            if event.get("type") != "Warning":
                continue
            key = (event.get("object") or "", event.get("reason") or "", event.get("uid") or "")
            result[key] = max(result.get(key, 0), event.get("count") or 1)
        return result

    if any(e.get("type") == "Warning" and not e.get("uid")
           for report in (before, after) for e in report["events"]):
        warnings.append("Legacy warning records without UID may not distinguish separate event series")
    old_events, new_events = warning_events(before), warning_events(after)
    for key, count in sorted(new_events.items()):
        target = "event/" + key[0]
        if key not in old_events:
            add("warning-first-captured", target, "Warning first captured: " + key[1], None, count)
        elif count > old_events[key]:
            add("warning-count-increased", target, "Observed warning counter increased: " + key[1],
                old_events[key], count)
    return {"schema_version": 1, "command": "compare",
            "context": before["context"], "namespace": before["namespace"],
            "before_time": before["created_at"], "after_time": after["created_at"],
            "has_changes": bool(findings), "findings": findings, "warnings": warnings}
