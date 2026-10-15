"""Kubernetes diagnostics and explicitly enabled recovery. Python 3.12 and kubectl."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from .compare import compare_files

MAX_OUTPUT = 8 * 1024 * 1024


class QueryError(Exception):
    """A command failed without exposing its possibly sensitive stderr."""


class Kube:
    def __init__(self, context, namespace):
        self.context, self.namespace = context, namespace

    def run(self, *arguments):
        command = ["kubectl", "--context", self.context, "--namespace",
                   self.namespace, "--request-timeout=10s", *arguments]
        try:
            result = subprocess.run(command, capture_output=True, timeout=20,
                                    check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise QueryError("kubectl unavailable or timed out") from error
        if result.returncode:
            raise QueryError("kubectl query failed; check context, access and resource name")
        if len(result.stdout) > MAX_OUTPUT:
            raise QueryError("query output exceeded the report input limit")
        return result.stdout.decode("utf-8", errors="replace")

    def get(self, resource, *arguments):
        try:
            return json.loads(self.run("get", resource, *arguments, "-o", "json"))
        except (ValueError, TypeError) as error:
            raise QueryError("kubectl returned invalid JSON") from error

    def reference_keys(self, kind, name):
        # Only names/keys leave kubectl. Secret values are never stored in reports.
        if not re.fullmatch(r"[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?", name):
            raise QueryError("Invalid reference name")
        template = ('{{.metadata.name}}{{"\\n"}}'
                    '{{range $key,$value := .data}}data:{{$key}}{{"\\n"}}{{end}}')
        template += '{{range $key,$value := .binaryData}}binary:{{$key}}{{"\\n"}}{{end}}'
        text = self.run("get", kind, name, "--ignore-not-found",
                        "-o", "go-template=" + template)
        return text.splitlines()


def quantity(value):
    text = str(value)
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]*)?|\.[0-9]+)([numkKMGTPE]|[KMGTPE]i)?", text)
    if not match:
        try:
            number = Decimal(text)
        except InvalidOperation as error:
            raise ValueError("unsupported resource quantity") from error
    else:
        factors = {"": 1, "n": Decimal("1e-9"), "u": Decimal("1e-6"),
                   "m": Decimal("1e-3"), "k": 1000, "K": 1000}
        factors.update({s: 1000 ** i for i, s in enumerate("MGTPE", 2)})
        factors.update({s + "i": 1024 ** i for i, s in enumerate("KMGTPE", 1)})
        number = Decimal(match.group(1)) * factors[match.group(2) or ""]
    if not number.is_finite() or number < 0 or abs(number.adjusted()) > 30:
        raise ValueError("resource quantities must be finite and nonnegative")
    return number


def pod_requests(spec):
    if spec.get("resources") or any(c.get("restartPolicy") == "Always"
                                   for c in spec.get("initContainers", [])):
        raise ValueError("pod-level resources and restartable init containers need scheduler analysis")
    result = {}
    for resource in ("cpu", "memory"):
        regular = sum((quantity(c.get("resources", {}).get("requests", {}).get(resource, 0))
                       for c in spec.get("containers", [])), Decimal(0))
        init = max((quantity(c.get("resources", {}).get("requests", {}).get(resource, 0))
                    for c in spec.get("initContainers", [])), default=Decimal(0))
        result[resource] = max(regular, init) + quantity(spec.get("overhead", {}).get(resource, 0))
    return result


def references(spec):
    for container in spec.get("containers", []) + spec.get("initContainers", []):
        for entry in container.get("envFrom", []):
            for field, kind in (("secretRef", "secret"), ("configMapRef", "configmap")):
                ref = entry.get(field)
                if ref and not ref.get("optional"):
                    yield kind, ref["name"], None, False
        for entry in container.get("env", []):
            source = entry.get("valueFrom", {})
            for field, kind in (("secretKeyRef", "secret"), ("configMapKeyRef", "configmap")):
                ref = source.get(field)
                if ref and not ref.get("optional"):
                    yield kind, ref["name"], ref["key"], False
    for volume in spec.get("volumes", []):
        sources = [volume] + volume.get("projected", {}).get("sources", [])
        for source in sources:
            for field, kind in (("secret", "secret"), ("configMap", "configmap")):
                ref = source.get(field)
                if ref and not ref.get("optional"):
                    name = ref.get("secretName") or ref.get("name")
                    if name:
                        items = ref.get("items", [])
                        if not items:
                            yield kind, name, None, True
                        for item in items:
                            yield kind, name, item["key"], True
    for ref in spec.get("imagePullSecrets", []):
        yield "secret", ref["name"], None, False


def check_capacity(kube, spec):
    desired = pod_requests(spec)
    nodes = kube.get("nodes").get("items", [])
    pods = kube.get("pods", "--all-namespaces").get("items", [])
    used = {}
    for pod in pods:
        if pod.get("status", {}).get("phase") in {"Succeeded", "Failed"}:
            continue
        node = pod.get("spec", {}).get("nodeName")
        if node:
            current = used.setdefault(node, {"cpu": Decimal(0), "memory": Decimal(0)})
            resources = pod_requests(pod["spec"])
            for key in current:
                current[key] += resources[key]
    fits = []
    for node in nodes:
        node_spec = node.get("spec", {})
        metadata = node.get("metadata", {})
        if node_spec.get("unschedulable"):
            continue
        if not any(c.get("type") == "Ready" and c.get("status") == "True"
                   for c in node.get("status", {}).get("conditions", [])):
            continue
        labels = metadata.get("labels", {})
        if any(labels.get(key) != value for key, value in spec.get("nodeSelector", {}).items()):
            continue
        # Conservatively exclude tainted nodes; matching tolerations needs scheduler analysis.
        if any(t.get("effect") in {"NoSchedule", "NoExecute"} for t in node_spec.get("taints", [])):
            continue
        name = metadata.get("name", "")
        allocated = used.get(name, {"cpu": Decimal(0), "memory": Decimal(0)})
        available = node.get("status", {}).get("allocatable", {})
        if all(quantity(available.get(key, 0)) - allocated[key] >= desired[key]
               for key in ("cpu", "memory")):
            fits.append(name)
    return fits


def check_record(checks, status, name, detail):
    checks.append({"status": status, "check": name, "detail": detail})


def preflight(kube, args):
    checks = []
    kube.get("namespace", args.namespace)
    check_record(checks, "PASS", "namespace", "Target namespace exists")
    if args.file or getattr(args, "chart", None):
        from .manifests import source_document
        document = source_document(args)
        candidates = document["items"]
        matches = [d for d in candidates if d.get("kind") == "Deployment"
                   and d.get("metadata", {}).get("name") == args.deployment
                   and d.get("metadata", {}).get("namespace", args.namespace) == args.namespace]
        if len(matches) != 1:
            raise ValueError("Manifest input must contain exactly one matching Deployment in the target namespace")
        deployment = matches[0]
        if deployment.get("metadata", {}).get("namespace", args.namespace) != args.namespace:
            raise ValueError("manifest namespace differs from --namespace")
    else:
        deployment = kube.get("deployment", args.deployment)
    spec = deployment["spec"]["template"]["spec"]
    containers = spec.get("containers", [])
    if not containers:
        check_record(checks, "FAIL", "containers", "No application containers found")
    for container in containers + spec.get("initContainers", []):
        name = container["name"]
        image = container.get("image", "")
        pinned = bool(re.fullmatch(r"[A-Za-z0-9._:/-]+@sha256:[a-f0-9]{64}", image))
        check_record(checks, "PASS" if pinned else "FAIL", "image:" + name,
                     "Digest is set" if pinned else "Use repository@sha256 followed by 64 lowercase hex characters")
        resources = container.get("resources", {})
        complete = all(key in resources.get(section, {}) for section in ("requests", "limits")
                       for key in ("cpu", "memory"))
        check_record(checks, "PASS" if complete else "FAIL", "resources:" + name,
                     "CPU/memory requests and limits set" if complete else "Set CPU/memory requests and limits")
        if complete:
            valid = all(quantity(resources["requests"][key]) <= quantity(resources["limits"][key])
                        for key in ("cpu", "memory"))
            check_record(checks, "PASS" if valid else "FAIL", "limits:" + name,
                         "Requests fit limits" if valid else "Request exceeds its limit")
        if container in containers:
            for probe in ("readinessProbe", "livenessProbe"):
                check_record(checks, "PASS" if container.get(probe) else "FAIL",
                             probe + ":" + name, "Configured" if container.get(probe) else "Missing probe")
        if args.verify_images and pinned:
            if not shutil.which("docker"):
                check_record(checks, "UNKNOWN", "registry:" + name, "Docker is required for image verification")
            else:
                try:
                    result = subprocess.run(["docker", "manifest", "inspect", image],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            timeout=30, check=False)
                    check_record(checks, "PASS" if result.returncode == 0 else "UNKNOWN",
                                 "registry:" + name, "Image accessible" if result.returncode == 0
                                 else "Cannot verify image; check digest, network and registry login")
                except (OSError, subprocess.TimeoutExpired):
                    check_record(checks, "UNKNOWN", "registry:" + name, "Registry inspection timed out or failed")
    if not args.verify_images:
        check_record(checks, "WARN", "registry", "Image existence/signature not checked; use --verify-images for existence")
    cache = {}
    for kind, name, key, binary_allowed in sorted(set(references(spec)),
                                                  key=lambda ref: (ref[0], ref[1], ref[2] or "", ref[3])):
        try:
            if (kind, name) not in cache:
                cache[kind, name] = kube.reference_keys(kind, name)
            lines = cache[kind, name]
            exists = bool(lines) and (key is None or "data:" + key in lines[1:]
                                      or (binary_allowed and "binary:" + key in lines[1:]))
            check_record(checks, "PASS" if exists else "FAIL", "reference:" + kind + "/" + name,
                         "Required reference exists" if exists else "Required object or data key is missing")
        except QueryError:
            check_record(checks, "UNKNOWN", "reference:" + kind + "/" + name,
                         "Reference cannot be checked with current access")
    try:
        fits = check_capacity(kube, spec)
        check_record(checks, "PASS" if fits else "UNKNOWN", "capacity",
                     f"{len(fits)} node(s) have estimated CPU/memory room for one new pod" if fits
                     else "No eligible headroom found; inspect capacity, taints and scheduling constraints")
    except (QueryError, ValueError):
        check_record(checks, "UNKNOWN", "capacity", "Capacity cannot be estimated with available access/resource types")
    check_record(checks, "WARN", "scheduler",
                 "Estimate is for one pod; affinity, topology, volumes, quotas, ports and full rollout are not simulated")
    check_record(checks, "WARN", "admission", "Admission policies and signatures are not evaluated by this tool")
    return {"checks": checks, "deployment": args.deployment,
            "configuration_source": "local manifest/Helm render" if args.file or getattr(args, "chart", None) else "live Deployment"}


def safe_image(value):
    return value if re.fullmatch(r"[A-Za-z0-9._:/@+-]{1,512}", value) else "[omitted]"


def redact(text):
    text = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
                  "[PRIVATE KEY REDACTED]", text, flags=re.S)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", text)
    text = re.sub(r"""(?i)((?:password|passwd|token|secret|api[_-]?key|authorization)["']?\s*[:=]\s*["']?)[^\s,;"']+""",
                  r"\1[REDACTED]", text)
    text = re.sub(r"(https?://)[^/\s@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[AWS KEY REDACTED]", text)
    return text


def write_private(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(text)


def incident(kube, args):
    directory = Path(args.output or ("reports/incident-" + uuid.uuid4().hex[:12]))
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(mode=0o700, exist_ok=False)
    os.chmod(directory, 0o700)
    report = {"pods": [], "deployments": [], "events": [], "unavailable": [], "logs": []}
    datasets = {}
    for kind in ("pods", "deployments", "events"):
        try:
            datasets[kind] = kube.get(kind).get("items", [])
        except QueryError:
            report["unavailable"].append(kind)
            datasets[kind] = []
    # Only selected fields are retained: no environment values, annotations or event messages.
    pods = sorted(datasets["pods"], key=lambda p: (
        p.get("status", {}).get("phase") == "Running" and
        bool(p.get("status", {}).get("containerStatuses")) and
        all(c.get("ready", False) for c in p.get("status", {}).get("containerStatuses", [])),
        p.get("metadata", {}).get("name", "")))[:args.max_pods]
    report["pod_count"] = len(datasets["pods"])
    report["pods_truncated"] = len(datasets["pods"]) > len(pods)
    log_budget = 20
    for pod in pods:
        metadata, status, spec = pod.get("metadata", {}), pod.get("status", {}), pod.get("spec", {})
        report["pods"].append({
            "name": metadata.get("name"), "uid": metadata.get("uid"), "phase": status.get("phase"),
            "node": spec.get("nodeName"),
            "containers": [{"name": s.get("name"), "ready": s.get("ready"),
                            "restarts": s.get("restartCount", 0),
                            "reason": next((v.get("reason") for v in s.get("state", {}).values()
                                            if isinstance(v, dict) and v.get("reason")), None)}
                           for s in status.get("containerStatuses", [])],
            "images": [safe_image(c.get("image", "")) for c in spec.get("containers", [])],
        })
        if args.include_logs:
            for container in spec.get("containers", [])[:3]:
                if log_budget == 0:
                    break
                log_budget -= 1
                try:
                    content = kube.run("logs", metadata["name"], "-c", container["name"],
                                       "--tail=50", "--since=10m", "--limit-bytes=65536")
                    filename = "log-" + str(len(report["logs"]) + 1) + ".txt"
                    write_private(directory / filename, redact(content))
                    report["logs"].append({"pod": metadata["name"], "container": container["name"],
                                           "file": filename})
                except QueryError:
                    report["unavailable"].append("logs:" + metadata["name"] + "/" + container["name"])
    from .recovery import fingerprint
    for deployment in datasets["deployments"][:100]:
        metadata, status = deployment.get("metadata", {}), deployment.get("status", {})
        report["deployments"].append({
            "name": metadata.get("name"), "uid": metadata.get("uid"), "generation": metadata.get("generation"),
            "template_sha256": fingerprint(deployment.get("spec", {}).get("template", {})),
            "observed_generation": status.get("observedGeneration"),
            "desired": deployment.get("spec", {}).get("replicas", 1),
            "ready": status.get("readyReplicas", 0), "updated": status.get("updatedReplicas", 0),
            "images": [safe_image(c.get("image", "")) for c in
                       deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])],
        })
    events = sorted(datasets["events"], key=lambda e: e.get("lastTimestamp") or
                    e.get("eventTime") or e.get("metadata", {}).get("creationTimestamp", ""))[-100:]
    for event in events:
        report["events"].append({
            "uid": event.get("metadata", {}).get("uid"),
            "type": event.get("type"), "reason": event.get("reason"),
            "count": event.get("count"), "time": event.get("lastTimestamp") or event.get("eventTime"),
            "object": event.get("involvedObject", {}).get("name"),
        })
    report["deployment_count"] = len(datasets["deployments"])
    report["event_count"] = len(datasets["events"])
    report["limitations"] = [
        "Snapshots are not atomic; they are observations, not a root-cause diagnosis.",
        "Event messages, annotations, environment values and secret objects are excluded.",
        "Logs are opt-in and redaction is best effort; manually review before sharing.",
        "At most 100 deployments, 100 events, selected pods and 20 current-container logs are retained.",
    ]
    return directory, report


def _main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    modules = {"diagnose": "diagnose", "recover": "recovery", "watch-recovery": "watch_recovery",
               "repair": "repair", "demo": "demo", "policy": "policy", "timeline": "timeline",
               "release-check": "release_check", "manifest-check": "manifest_check",
               "drift": "drift", "repair-dry-run": "repair_dry_run", "bundle": "bundle",
               "doctor": "doctor", "guide": "guide", "report": "report", "handover": "handover",
               "example": "example", "gitops-propose": "gitops_propose", "suggest": "suggest"}
    if arguments and arguments[0] in modules:
        from importlib import import_module
        return import_module("." + modules[arguments[0]], __package__).main(arguments[1:])
    parser = argparse.ArgumentParser(prog="devops-toolkit", epilog="Operational commands support --notify-config PATH for optional outcome alerts. See docs/alerts.md.")
    from . import __version__
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("repair", help="Monitor and restore approved container settings, replicas or Service selector")
    subcommands.add_parser("demo", help="Create a disposable local kind recovery demonstration")
    subcommands.add_parser("diagnose", help="Read workload symptoms and recommended actions")
    subcommands.add_parser("recover", help="Preview or execute policy-bound image recovery")
    subcommands.add_parser("watch-recovery", help="Monitor one rollout and automatically recover approved failure")
    subcommands.add_parser("policy", help="Create private repair policy from live UIDs and your approved fix")
    subcommands.add_parser("timeline", help="Correlate saved snapshots and scoped repair audits offline")
    subcommands.add_parser("release-check", help="Explain image, config, capacity, Service, availability and recovery risks")
    subcommands.add_parser("manifest-check", help="Check YAML/JSON/Helm configuration offline for CI")
    subcommands.add_parser("drift", help="Compare desired manifest fields with live Deployment/Service state")
    subcommands.add_parser("repair-dry-run", help="Validate an approved patch using Kubernetes server dry-run")
    subcommands.add_parser("bundle", help="Collect a private ownership-scoped workload troubleshooting bundle")
    for name, help_text in {
        "suggest": "Suggest investigation, resolution and verification steps without executing them",
        "doctor": "Check prerequisites; cluster authorization queries are opt-in",
        "guide": "Interactively plan a command without executing it",
        "report": "Export saved evidence as local HTML, Markdown or summary JSON",
        "handover": "Create a private incident handover draft from saved evidence",
        "example": "Write a fabricated offline troubleshooting example",
        "gitops-propose": "Create a local image-only source change proposal for review",
    }.items():
        subcommands.add_parser(name, help=help_text)
    for name in ("preflight", "incident"):
        command = subcommands.add_parser(name, help=(
            "Check deployment configuration" if name == "preflight"
            else "Collect private namespace evidence"))
        command.add_argument("--context", required=True, help="Explicit kubectl context; never switched")
        command.add_argument("--namespace", default="platform")
        command.add_argument("--output", help="New private JSON file (preflight) or new directory (incident)")
        if name == "preflight":
            command.add_argument("--deployment", default="platform")
            from .manifests import source_arguments
            source_arguments(command)
            command.add_argument("--verify-images", action="store_true")
        else:
            command.add_argument("--include-logs", action="store_true")
            command.add_argument("--max-pods", type=int, choices=range(1, 51), default=10, metavar="1..50")
    compare = subcommands.add_parser("compare", help="Compare two saved snapshots offline")
    compare.add_argument("before", help="Earlier incident report.json")
    compare.add_argument("after", help="Later incident report.json")
    compare.add_argument("--output", help="New private JSON comparison file")
    compare.add_argument("--fail-on-change", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "compare":
        try:
            report = compare_files(args.before, args.after)
            if args.output:
                write_private(Path(args.output), json.dumps(report, indent=2) + "\n")
            for finding in report["findings"]:
                resource = json.dumps(finding["resource"], ensure_ascii=True)[1:-1]
                message = json.dumps(finding["message"], ensure_ascii=True)[1:-1]
                values = ""
                if finding["before"] is not None or finding["after"] is not None:
                    values = " | " + json.dumps(finding["before"], ensure_ascii=True) + " -> " + json.dumps(finding["after"], ensure_ascii=True)
                print("CHANGE " + resource + ": " + message + values)
            if not report["findings"]:
                print("No differences in the captured fields. This is not a health check.")
            for warning in report["warnings"]:
                print("NOTE: " + json.dumps(warning, ensure_ascii=True)[1:-1])
            return 1 if args.fail_on_change and report["has_changes"] else 0
        except (OSError, ValueError, KeyError, TypeError):
            print("Cannot compare: use valid incident snapshots from the same context/namespace, "
                  "in time order, and a new output file.", file=sys.stderr)
            return 2
    if not args.context.strip() or args.context.startswith("-") or not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", args.namespace):
        parser.error("Use a context name and a valid namespace name")
    if args.command == "preflight" and not re.fullmatch(r"[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?", args.deployment):
        parser.error("Use a valid Deployment name")
    kube = Kube(args.context, args.namespace)
    metadata = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                "context": args.context, "namespace": args.namespace}
    try:
        if args.command == "preflight":
            report = {**metadata, **preflight(kube, args)}
            if args.output:
                write_private(Path(args.output), json.dumps(report, indent=2) + "\n")
            for check in report["checks"]:
                print(f"{check['status']:7} {check['check']}: {check['detail']}")
            states = {c["status"] for c in report["checks"]}
            return 1 if "FAIL" in states else 2 if "UNKNOWN" in states else 0
        directory, evidence = incident(kube, args)
        report = {**metadata, **evidence}
        write_private(directory / "report.json", json.dumps(report, indent=2) + "\n")
        print("Saved private evidence to " + str(directory))
        if report["unavailable"]:
            print("Collection is partial; see unavailable in report.json")
        return 2 if report["unavailable"] else 0
    except (QueryError, OSError, ValueError, KeyError, TypeError, AttributeError):
        print("Unable to complete: check context, permissions, input shape and a new output path. "
              "No cluster changes were made.", file=sys.stderr)
        return 2


def main(argv=None):
    from .alerts import invoke
    arguments = list(sys.argv[1:] if argv is None else argv)
    code = invoke(arguments, _main)
    from .suggest import failure_hint
    hint = failure_hint(arguments, code)
    if hint:
        print(hint, file=sys.stderr)
    return code
