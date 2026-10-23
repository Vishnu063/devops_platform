# DevOps LiveFlow (preview)

A lightweight read-only live infrastructure graph integrated as an isolated optional component of the DevOps Platform Toolkit. No new Python packages, AI API, database or GPU are required. It observes local Docker containers, images and networks. Optionally it also observes a selected Kubernetes namespace and Jenkins pipeline. The existing CLI is unchanged.

## Quick start on EC2/Linux

```bash
cd devops_platform
python3 liveflow/server.py
```

LiveFlow binds **only** to `127.0.0.1:8769`. On the EC2 host open `http://127.0.0.1:8769`. On another computer create an SSH tunnel:

```bash
ssh -N -L 8769:127.0.0.1:8769 ubuntu@YOUR_EC2_PUBLIC_IP
```

Then open `http://127.0.0.1:8769` on that same computer. Do **not** open port 8769 in the EC2 security group or publicly reverse-proxy this unauthenticated preview. You need Python >=3.12 and local Docker CLI access. Docker group access is effectively root-equivalent: avoid running the app as root or weakening socket permissions.

## Kubernetes (optional)

```bash
kubectl config get-contexts
python3 liveflow/server.py --context YOUR_KUBECTL_CONTEXT --namespace default
```

The selected identity needs only `get/list` on Deployments, Pods, and Services. No write operations. Selector connections are label matches; they are **not** a proof of ownership or real network traffic. A failed Kubernetes call marks previous resources unknown and shows a source warning. It never counts API failures as deletions.

## Jenkins (optional)

```bash
export LIVEFLOW_JENKINS_USER=read-only-user
export LIVEFLOW_JENKINS_TOKEN=your-token
python3 liveflow/server.py --jenkins-url http://127.0.0.1:8081 --jenkins-job cloudlaunch-pipeline
```

The UI can show last build status and, when the Jenkins Pipeline REST API `wfapi/describe` is available, its stages. Provide **both** Jenkins arguments. Use HTTPS for any non-loopback Jenkins server. Never store tokens in Git. You can combine all optional arguments in one command.

## Changes you can see

- Docker container added or deleted: corresponding node and in-memory timeline update on the next successful snapshot.
- Docker network/image connections change when container configuration changes.
- Kubernetes Pod, Service or Deployment added/deleted/updated in the selected namespace: nodes/status changes.
- Jenkins build/stage changes: stages update after a build runs, not merely because the Jenkinsfile was edited.
- Stopped/failed containers and unready pods: warning/error styling.

The dashboard polls every five seconds, so extremely short-lived resources may be missed. The first snapshot is only discovery (not a burst of false creation events). Timeline events are memory-only, limited to 60 entries, and disappear on restart. Data collection failure never creates fake deletion events. It is **not yet** a full AWS EC2/VPC/ALB graph or a proven source-to-production pipeline correlation system.

No real running infrastructure was connected or validated as part of this development change. This is a preview to exercise against disposable test resources before relying on it operationally.