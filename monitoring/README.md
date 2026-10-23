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
