# DevOps Platform Monitoring

The Flask app already exports Prometheus metrics at `/metrics`. This optional local stack adds Prometheus (7-day metrics retention) and a provisioned Grafana dashboard. It is intentionally **not public** and requires no cloud API keys.

## Start on EC2

```bash
cd ~/devops_platform
read -rsp "New Grafana admin password: " GRAFANA_ADMIN_PASSWORD; echo
export GRAFANA_ADMIN_PASSWORD
docker compose -f compose.yml -f monitoring/compose.yml up -d --no-build --no-deps prometheus grafana
docker compose -f compose.yml -f monitoring/compose.yml ps prometheus grafana
curl -fsS http://127.0.0.1:9090/-/ready
```

Prometheus scrapes `http://api:8080/metrics` over the private Compose network every 15 seconds. Grafana connects to Prometheus with the auto-provisioned data source and includes a dashboard under **Dashboards → DevOps Platform**.

## Access securely from your Mac

Open a **new** Mac terminal (leave the tunnel connected):
```bash
ssh -i PowerRangers123.pem -L 13000:127.0.0.1:3000 -L 19090:127.0.0.1:9090 ubuntu@YOUR_EC2_PUBLIC_IP
```
Then open **http://localhost:13000** (Grafana, username `admin` and the password you selected) or **http://localhost:19090** (Prometheus). The key path and IP must match your current machine.

## Verify actual scraping

In Prometheus query `up{job="devops-platform"}` — **1** means the application exporter is reachable, **0** means it is not. Visit `http://127.0.0.1:8080/` on EC2 to generate a normal request counted by Flask metrics. Empty graphs can also mean no traffic yet; this app intentionally excludes health endpoints from request-rate charts.

## Scope and security

Both interfaces bind to **127.0.0.1 only**, not EC2 public ports. Do not open ports 3000 or 9090 in the security group. Credentials are passed via an environment variable and are not committed. The Grafana admin password initializes the account only when the Grafana volume is new; change it in Grafana if needed. Metrics and dashboard data reside in named Docker volumes. This stack is **optional** and not part of the Jenkins app replacement path; it has not been verified on your EC2 until you run it.

To stop monitoring (preserving its volumes):
```bash
docker compose -f compose.yml -f monitoring/compose.yml stop prometheus grafana
```

## Infrastructure monitoring (EC2 + Docker)

Additional services: Node Exporter (Linux CPU/RAM/disk/network) and cAdvisor (Docker resource metrics). Neither exposes a public host port. cAdvisor runs **privileged** with host filesystem mounts; use this configuration only on a dedicated/trusted lab host and review the risk before production use. Memory limits: Node Exporter 64 MiB, cAdvisor 192 MiB, Prometheus 256 MiB, Grafana 384 MiB.

On EC2, after pulling new code, start the exporters and recreate Prometheus/Grafana to pick up provisioned files:
```bash
cd ~/devops_platform
read -rsp 'Grafana admin password (existing password is fine): ' GRAFANA_ADMIN_PASSWORD; echo
export GRAFANA_ADMIN_PASSWORD
docker compose -f compose.yml -f monitoring/compose.yml up -d --no-build --no-deps node-exporter cadvisor prometheus grafana
```

Check targets at `http://127.0.0.1:9090/api/v1/targets`. All three jobs (`devops-platform`, `node`, `cadvisor`) should show **up**. For a short query:
```bash
curl -s 'http://127.0.0.1:9090/api/v1/query?query=up'
```
Open the existing Grafana dashboard to view six additional host/container charts. If Docker panels show no data even though `up{job="cadvisor"}=1`, inspect cAdvisor's available container metric labels and adjust dashboard filters; cAdvisor versions expose different labels.

Prometheus evaluates alerts in `monitoring/alerts.yml` for application down, exporter down, high CPU/RAM, and low root-disk space. View firing/pending alerts under **Prometheus → Alerts**. **No notification destination has been configured**, so alerts are local only; external email/Slack delivery requires a receiver and separate explicit credentials/configuration.

Do not open EC2 inbound ports 9100, 8080 (cAdvisor), 3000, or 9090. These exporters only connect inside the Docker Compose network.
