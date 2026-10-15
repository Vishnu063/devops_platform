"""A disposable kind demonstration of approved automatic image recovery.

Never accepts an existing context. All writes target a newly named local cluster.
"""
import argparse
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
            "annotations": {PREFIX + "allow-image-recovery": "true"}},
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
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": APP, "namespace": NAMESPACE},
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
             "Demo cluster retained: " + str(report.get("cluster_retained", False)), "",
             "| Stage | Result |", "| --- | --- |"]
    lines.extend("| " + s["stage"] + " | " + s["status"] + " |" for s in report["stages"])
    lines += ["", "Checks: healthy HTTP response before and after repair, observed failed rollout,",
              "approved image restored, exactly one acknowledged repair, and repeat invocation refused.",
              "Only stages marked PASS were observed. Remaining stages were not completed.", "",
              "The kubeconfig and approval policy are private local files. Do not upload them.", ""]
    return "\n".join(lines)


def run_demo(output=None, keep_cluster=False):
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
              "cluster": cluster, "created_at": datetime.now(timezone.utc).isoformat(),
              "node_image": NODE_IMAGE, "approved_image": GOOD_IMAGE,
              "result": "INCOMPLETE", "cluster_retained": keep_cluster, "stages": []}
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
        passed(stage)
        stage = "deploy healthy application"
        kubectl("apply", "-f", "-", input_text=json.dumps(manifests()))
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
        stage = "introduce bad image in demo workload"
        kubectl("set", "image", "deployment/" + APP, "web=" + BAD_IMAGE)
        passed(stage)
        stage = "observe failed rollout"
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            deployment = get("deployment", APP)
            if failed_rollout(deployment):
                break
            time.sleep(3)
        else:
            raise DemoError("Failed rollout condition was not observed")
        passed(stage)
        toolkit("incident", "--context", context, "--namespace", NAMESPACE,
                "--output", str(directory / "failed"))
        write_json(directory / "recovery-policy.local.json",
                   policy_for(deployment, get("namespace", NAMESPACE), context))
        stage = "automatic image recovery"
        watcher = toolkit("watch-recovery", "--policy", str(directory / "recovery-policy.local.json"),
                          "--execute", "--audit", str(directory / "recovery.jsonl"),
                          "--interval", "5", "--max-wait", "120", "--recovery-timeout", "180",
                          timeout=360)
        write_private(directory / "monitor.txt", watcher.stdout)
        current = get("deployment", APP)
        if current["spec"]["template"]["spec"]["containers"][0]["image"] != GOOD_IMAGE:
            raise DemoError("Approved image was not restored")
        if not current["metadata"].get("annotations", {}).get(PREFIX + "recovery-attempt"):
            raise DemoError("Persistent attempt latch missing")
        records = [json.loads(line) for line in (directory / "recovery.jsonl").read_text().splitlines()]
        if sum(r["event"] == "patch_acknowledged" for r in records) != 1 or not any(
                r["event"] == "deployment_ready" for r in records):
            raise DemoError("Audit does not confirm one ready recovery")
        passed(stage)
        stage = "HTTP response after recovery"
        verify_http()
        passed(stage)
        stage = "repeat recovery refused"
        repeat_audit = directory / "repeat-must-not-exist.jsonl"
        repeat = toolkit("recover", "--policy", str(directory / "recovery-policy.local.json"),
                         "--execute", "--audit", str(repeat_audit), allowed=(2,))
        if repeat.returncode != 2 or repeat_audit.exists():
            raise DemoError("Repeat recovery was not refused before mutation")
        passed(stage)
        toolkit("incident", "--context", context, "--namespace", NAMESPACE,
                "--output", str(directory / "after"))
        comparison = toolkit("compare", str(directory / "failed/report.json"),
                             str(directory / "after/report.json"), "--output", str(directory / "comparison.json"))
        write_private(directory / "comparison.txt", comparison.stdout)
        report["result"] = "PASS"
    except (DemoError, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt):
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
    args = parser.parse_args(argv)
    try:
        return run_demo(args.output, args.keep_cluster)
    except (DemoError, OSError) as error:
        print(str(error) if isinstance(error, DemoError) else "Cannot create a new private evidence directory.", file=sys.stderr)
        return 2
