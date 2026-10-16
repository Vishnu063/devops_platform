"""A disposable kind demonstration of approved automatic image recovery.

Never accepts an existing context. All writes target a newly named local cluster.
"""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from .cli import write_private
from .recovery import fingerprint, PREFIX
from .watch_recovery import failed_rollout

NODE_IMAGE = "kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
GOOD_IMAGE = "docker.io/library/python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258"
BAD_IMAGE = "docker.io/library/python@sha256:" + "0" * 64
NAMESPACE, APP = "devops-demo", "recovery-demo"
RESPONSE = "devops-platform-demo"
SERVER = '''from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"devops-platform-demo\\n"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
'''


class DemoError(Exception):
    pass


def manifests(image=GOOD_IMAGE):
    labels = {"app": APP}
    return {"apiVersion": "v1", "kind": "List", "items": [
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE,
         "labels": {"pod-security.kubernetes.io/enforce": "restricted"}}},
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {
            "name": APP, "namespace": NAMESPACE,
            "annotations": {PREFIX + "allow-image-recovery": "true", PREFIX + "allow-repair": "true"}},
         "spec": {"replicas": 1, "progressDeadlineSeconds": 60,
                  "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1}},
                  "selector": {"matchLabels": labels}, "template": {"metadata": {"labels": labels},
                  "spec": {"automountServiceAccountToken": False,
                           "nodeSelector": {"kubernetes.io/arch": "amd64", "kubernetes.io/os": "linux"},
                           "securityContext": {"runAsNonRoot": True, "runAsUser": 10001,
                                               "seccompProfile": {"type": "RuntimeDefault"}},
                           "containers": [{"name": "web", "image": image, "imagePullPolicy": "IfNotPresent",
                               "command": ["python", "-c", SERVER], "workingDir": "/tmp",
                               "ports": [{"name": "http", "containerPort": 8080}],
                               "readinessProbe": {"httpGet": {"path": "/", "port": "http"}, "periodSeconds": 2},
                               "livenessProbe": {"httpGet": {"path": "/", "port": "http"}, "initialDelaySeconds": 5},
                               "resources": {"requests": {"cpu": "25m", "memory": "32Mi"},
                                             "limits": {"cpu": "250m", "memory": "128Mi"}},
                               "securityContext": {"allowPrivilegeEscalation": False,
                                                   "readOnlyRootFilesystem": True,
                                                   "capabilities": {"drop": ["ALL"]}},
                               "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}]}],
                           "volumes": [{"name": "tmp", "emptyDir": {"sizeLimit": "16Mi"}}]}}}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": APP, "namespace": NAMESPACE,
            "annotations": {PREFIX + "allow-repair": "true"}},
         "spec": {"selector": labels, "ports": [{"name": "http", "port": 8080, "targetPort": "http"}]}}
    ]}


def policy_for(deployment, namespace, context):
    return {"context": context, "namespace": NAMESPACE,
            "namespace_uid": namespace["metadata"]["uid"], "deployment": APP,
            "deployment_uid": deployment["metadata"]["uid"],
            "failed_template_sha256": fingerprint(deployment["spec"]["template"]),
            "approved_images": {"web": GOOD_IMAGE},
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()}


def prerequisites():
    missing = [name for name in ("docker", "kind", "kubectl") if shutil.which(name) is None]
    if sys.version_info < (3, 12):
        missing.append("Python 3.12+")
    if os.environ.get("DOCKER_HOST") and not os.environ["DOCKER_HOST"].startswith(("unix://", "npipe://")):
        raise DemoError("Use a local Docker daemon for this demo")
    if missing:
        raise DemoError("Install prerequisites first: " + ", ".join(missing))
    # The pinned Python image is the Linux amd64 image used by this repository.
    import platform
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        raise DemoError("This pinned demo currently requires an amd64 host")


def command(args, *, env, timeout=30, allowed=(0,), input_text=None):
    try:
        result = subprocess.run(args, input=input_text, text=True, capture_output=True,
                                env=env, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DemoError("Command unavailable or timed out; inspect the recorded demo stage") from error
    if result.returncode not in allowed:
        raise DemoError("Command failed; inspect the demo cluster and the recorded stage")
    return result


def write_json(path, value):
    write_private(path, json.dumps(value, indent=2) + "\n")


def summary(report):
    lines = ["# Local recovery demo", "", "Result: **" + report["result"] + "**", "",
             "This report describes one local demo run, not production validation.", "",
             "Scenario: " + report.get("scenario", "images"), "",
             "Demo cluster retained: " + str(report.get("cluster_retained", False)), "",
             "| Stage | Result |", "| --- | --- |"]
    lines.extend("| " + s["stage"] + " | " + s["status"] + " |" for s in report["stages"])
    lines += ["", "Checks: expected HTTP response before and after repair, observed scenario fault,",
              "approved correction restored, exactly one acknowledged repair, and repeat invocation refused.",
              "Only stages marked PASS were observed. Remaining stages were not completed.", "",
              "The kubeconfig and approval policy are private local files. Do not upload them.", ""]
    return "\n".join(lines)


def selector_fault_observed(target, slices):
    """An empty or null API endpoint list has no ready endpoints."""
    return target['spec'].get('selector') == {'app': 'wrong-demo-selector'} and not any(
        (endpoint.get('conditions') or {}).get('ready') is True
        for item in slices for endpoint in (item.get('endpoints') or []))


def run_demo(output=None, keep_cluster=False, scenario="images"):
    prerequisites()  # No files or clusters created when prerequisites are missing.
    run_id = uuid.uuid4().hex[:12]
    cluster, context = "devops-demo-" + run_id, "kind-devops-demo-" + run_id
    directory = Path(output or ("reports/demo-" + run_id)).resolve()
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(mode=0o700)  # Existing evidence is never overwritten.
    os.chmod(directory, 0o700)
    env = {**os.environ, "KUBECONFIG": str(directory / "kubeconfig.local"),
           "KIND_EXPERIMENTAL_PROVIDER": "docker"}
    report = {"kind": "local-recovery-demo", "schema_version": 1, "run_id": run_id,
              "cluster": cluster, "python_version": sys.version.split()[0], "created_at": datetime.now(timezone.utc).isoformat(),
              "node_image": NODE_IMAGE, "approved_image": GOOD_IMAGE,
              "result": "INCOMPLETE", "scenario": scenario, "cluster_retained": keep_cluster, "stages": []}
    stage, cluster_attempted = "prerequisites", False

    def passed(label):
        report["stages"].append({"stage": label, "status": "PASS"})
        print("PASS " + label, flush=True)

    def kubectl(*args, timeout=30, **kwargs):
        return command(["kubectl", "--kubeconfig", env["KUBECONFIG"], "--context", context,
                        "--namespace", NAMESPACE, "--request-timeout=15s", *args],
                       env=env, timeout=timeout, **kwargs)

    def get(kind, name):
        return json.loads(kubectl("get", kind, name, "-o", "json").stdout)

    def verify_http():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                response = kubectl("get", "--raw", f"/api/v1/namespaces/{NAMESPACE}/services/{APP}:http/proxy/").stdout.strip()
                if response == RESPONSE:
                    return
            except DemoError:
                pass  # Ready EndpointSlices can lag the Deployment condition briefly.
            time.sleep(2)
        raise DemoError("Expected demo HTTP response was not observed")

    def toolkit(*args, timeout=60, **kwargs):
        return command([sys.executable, "-m", "devops_toolkit", *args], env=env,
                       timeout=timeout, **kwargs)

    try:
        command(["docker", "info", "--format", "{{.ServerVersion}}"], env=env)
        endpoint = command(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], env=env).stdout.strip()
        if not endpoint.startswith(("unix://", "npipe://")):
            raise DemoError("Demo requires a local Docker endpoint")
        clusters = command(["kind", "get", "clusters"], env=env).stdout.splitlines()
        if cluster in clusters:
            raise DemoError("Generated name already exists; refusing to adopt a cluster")
        report["kind_version"] = command(["kind", "version"], env=env).stdout.strip()
        passed(stage)
        stage = "create separate local cluster"
        cluster_attempted = True
        command(["kind", "create", "cluster", "--name", cluster, "--image", NODE_IMAGE,
                 "--kubeconfig", env["KUBECONFIG"], "--wait", "180s"], env=env, timeout=360)
        os.chmod(env["KUBECONFIG"], 0o600)
        versions = json.loads(command(["kubectl", "--kubeconfig", env["KUBECONFIG"], "--context", context,
                                       "version", "-o", "json"], env=env).stdout)
        report["kubectl_version"] = versions["clientVersion"]["gitVersion"]
        report["kubernetes_version"] = versions["serverVersion"]["gitVersion"]
        passed(stage)
        stage = "deploy healthy application"
        desired_manifest = manifests()
        if scenario == "replicas":
            desired_manifest["items"][1]["spec"]["replicas"] = 2
        kubectl("apply", "-f", "-", input_text=json.dumps(desired_manifest))
        # kubectl's request timeout must allow the rollout watch to finish.
        command(["kubectl", "--kubeconfig", env["KUBECONFIG"], "--context", context,
                 "-n", NAMESPACE, "rollout", "status", "deployment/" + APP, "--timeout=240s"],
                env=env, timeout=260)
        passed(stage)
        stage = "HTTP response before failure"
        verify_http()
        passed(stage)
        toolkit("incident", "--context", context, "--namespace", NAMESPACE,
                "--output", str(directory / "before"))
        baseline = get("deployment", APP)
        stage = "introduce demo " + scenario + " fault"
        target_kind, action, approved = "Deployment", "images", {"web": GOOD_IMAGE}
        if scenario == "images":
            kubectl("set", "image", "deployment/" + APP, "web=" + BAD_IMAGE)
        elif scenario == "selector":
            target_kind, action, approved = "Service", "selector", {"app": APP}
            kubectl("patch", "service", APP, "--type=json", "-p", json.dumps([
                {"op": "replace", "path": "/spec/selector", "value": {"app": "wrong-demo-selector"}}]))
        elif scenario == "replicas":
            action, approved = "replicas", 2
            kubectl("scale", "deployment/" + APP, "--replicas=1")
        elif scenario == "configuration":
            action = "containers"
            healthy_probe = copy.deepcopy(baseline["spec"]["template"]["spec"]["containers"][0]["readinessProbe"])
            approved = {"web": {"readinessProbe": healthy_probe}}
            broken_probe = copy.deepcopy(healthy_probe)
            broken_probe["httpGet"]["port"] = 8081
            kubectl("patch", "deployment", APP, "--type=json", "-p", json.dumps([
                {"op": "replace", "path": "/spec/template/spec/containers/0/readinessProbe", "value": broken_probe}]))
        else:
            raise DemoError("Unsupported scenario")
        passed(stage)
        stage = "observe demo fault"
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            target = get(target_kind, APP)
            if scenario in {"images", "configuration"}:
                observed = failed_rollout(target)
            elif scenario == "selector":
                slices = json.loads(kubectl("get", "endpointslices", "-l", "kubernetes.io/service-name=" + APP, "-o", "json").stdout)["items"]
                observed = selector_fault_observed(target, slices)
            else:
                observed = target["spec"].get("replicas") == 1 and target.get("status", {}).get("replicas") == 1
            if observed:
                break
            time.sleep(3)
        else:
            raise DemoError("Expected demo fault was not observed")
        passed(stage)
        toolkit("incident", "--context", context, "--namespace", NAMESPACE,
                "--output", str(directory / "failed"))
        namespace = get("namespace", NAMESPACE)
        if scenario == "images":
            approval = policy_for(target, namespace, context)
            recovery_command, extra_timeout, latch = "watch-recovery", "--recovery-timeout", "recovery-attempt"
        else:
            approval = {"context": context, "namespace": NAMESPACE, "namespace_uid": namespace["metadata"]["uid"],
                        "kind": target_kind, "name": APP, "uid": target["metadata"]["uid"],
                        "failed_spec_sha256": fingerprint(target["spec"]), "action": action, "approved": approved,
                        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()}
            recovery_command, extra_timeout, latch = "repair", "--timeout", "repair-attempt"
        policy_path = directory / "recovery-policy.local.json"
        write_json(policy_path, approval)
        stage = "automatic approved " + action + " recovery"
        watcher = toolkit(recovery_command, "--policy", str(policy_path), "--execute",
                          "--audit", str(directory / "recovery.jsonl"), "--interval", "5",
                          "--max-wait", "120", extra_timeout, "180", timeout=360)
        write_private(directory / "monitor.txt", watcher.stdout)
        current = get(target_kind, APP)
        if scenario == "images":
            restored = current["spec"]["template"]["spec"]["containers"][0]["image"] == GOOD_IMAGE
        elif scenario == "selector":
            restored = current["spec"]["selector"] == approved
        elif scenario == "replicas":
            restored = current["spec"]["replicas"] == approved
        else:
            restored = current["spec"]["template"]["spec"]["containers"][0]["readinessProbe"] == healthy_probe
        if not restored or not current["metadata"].get("annotations", {}).get(PREFIX + latch):
            raise DemoError("Approved correction or persistent attempt latch missing")
        records = [json.loads(line) for line in (directory / "recovery.jsonl").read_text().splitlines()]
        if sum(r["event"] == "patch_acknowledged" for r in records) != 1 or not any(
                r["event"] in {"deployment_ready", "readiness_confirmed"} for r in records):
            raise DemoError("Audit does not confirm one ready recovery")
        passed(stage)
        stage = "HTTP response after recovery"
        verify_http()
        passed(stage)
        stage = "repeat recovery refused"
        repeat_audit = directory / "repeat-must-not-exist.jsonl"
        repeat = toolkit("recover" if scenario == "images" else "repair", "--policy", str(directory / "recovery-policy.local.json"),
                         "--execute", "--audit", str(repeat_audit), allowed=(2,))
        if repeat.returncode != 2 or repeat_audit.exists():
            raise DemoError("Repeat recovery was not refused before mutation")
        passed(stage)
        stage = "capture and correlate recovery evidence"
        toolkit("incident", "--context", context, "--namespace", NAMESPACE,
                "--output", str(directory / "after"))
        comparison = toolkit("compare", str(directory / "failed/report.json"),
                             str(directory / "after/report.json"), "--output", str(directory / "comparison.json"))
        write_private(directory / "comparison.txt", comparison.stdout)
        toolkit("timeline", str(directory / "before/report.json"), str(directory / "failed/report.json"),
                str(directory / "after/report.json"), "--audit", str(directory / "recovery.jsonl"),
                "--output", str(directory / "timeline.md"))
        passed(stage)
        report["result"] = "PASS"
    except (DemoError, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt) as error:
        report["failure_type"] = type(error).__name__
        report["stages"].append({"stage": stage, "status": "FAIL"})
        report["result"] = "FAIL"
        print("FAIL " + stage + "; inspect local evidence. No recovery retry was made.", file=sys.stderr)
    finally:
        if cluster_attempted and not keep_cluster:
            try:
                command(["kind", "delete", "cluster", "--name", cluster,
                         "--kubeconfig", env["KUBECONFIG"]], env=env, timeout=120)
                report["cluster_retained"] = False
                passed("remove demo cluster")
            except DemoError:
                report["cluster_retained"] = True
                report["result"] = "FAIL"
                report["stages"].append({"stage": "remove demo cluster", "status": "FAIL"})
                print("Cleanup failed: kind delete cluster --name " + cluster, file=sys.stderr)
        write_json(directory / "results.json", report)
        write_private(directory / "summary.md", summary(report))
        print("Evidence: " + str(directory), flush=True)
    return 0 if report["result"] == "PASS" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m devops_toolkit demo")
    parser.add_argument("--output", help="New private evidence directory; default reports/demo-UNIQUE-ID")
    parser.add_argument("--keep-cluster", action="store_true", help="Keep this demo's cluster for inspection")
    parser.add_argument("--scenario", choices=["images", "selector", "replicas", "configuration", "all"], default="images")
    args = parser.parse_args(argv)
    try:
        if args.scenario != "all":
            return run_demo(args.output, args.keep_cluster, args.scenario)
        prerequisites()
        parent = Path(args.output or ("reports/demo-all-" + uuid.uuid4().hex[:12])).resolve()
        parent.mkdir(parents=True, mode=0o700)
        os.chmod(parent, 0o700)
        results = []
        for scenario in ("images", "selector", "replicas", "configuration"):
            code = run_demo(str(parent / scenario), args.keep_cluster, scenario)
            results.append({"scenario": scenario, "exit_code": code})
            if code:
                break
        write_json(parent / "results.json", {"kind": "demo-scenarios", "runs": results,
                                              "result": "PASS" if len(results) == 4 and not any(r["exit_code"] for r in results) else "FAIL"})
        return 0 if len(results) == 4 and not any(r["exit_code"] for r in results) else 1
    except (DemoError, OSError) as error:
        print(str(error) if isinstance(error, DemoError) else "Cannot create a new private evidence directory.", file=sys.stderr)
        return 2
