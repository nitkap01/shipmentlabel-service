# shipmentlabel-service on AWS (SHIP-6, 09_10_2026)

**Open:** https://15.206.156.154 — log in with `ADMIN_PASSWORD` (kept on INDIE in `~/.secrets/shipmentlabel.env`, mode 600;
never in git or on Tasking).

## What runs where
| Item | Value |
|---|---|
| AWS account / CLI profile | 463946129264 / `--profile greenshadow` (region ap-south-1, Mumbai) |
| Server | `i-0472d264afe728c60` "shipmentlabel": t4g.large (2 vCPU ARM, 8 GB) Ubuntu 24.04, 30 GB gp3 encrypted, 2 GB swap |
| Public IP | Elastic IP **15.206.156.154** (`eipalloc-0512266e3a5631241`) |
| Firewall | `sg-0f6eca17b5f8beb79`: 443 + 80 public; 22 only from INDIE 110.235.227.56/32; 3000/8000/5432 closed |
| Access | `ssh ubuntu@15.206.156.154` from INDIE (key `shipmentlabel-indie`); fallback: AWS console → Session Manager (role `shipmentlabel-ec2-ssm`) |
| Backup bucket | `shipmentlabel-backup-463946129264` (S3, private, encrypted, versioned; old versions and database copies kept 90 days; server may put/get/list, not delete) |
| Budget | `shipmentlabel-monthly-90usd`: email above $90 actual or forecast (navbajaj2012@gmail.com, officialnitinkapoor@gmail.com) |
| Cost | ≈ $39/month (server $32.70, disk $2.75, IP $3.65) + data beyond 100 GB/month |
| Not created | EBS snapshots, domain, VPC/NAT, load balancer, RDS, Route 53, ECR |

## On the server (`/opt/shipmentlabel/app`)
- Stack: `postgres`, `backend` (127.0.0.1:8000), `web` (127.0.0.1:3000), `caddy` (80 → 443).
- HTTPS: Let's Encrypt **IP-address certificate** (shortlived profile, ~6 days, Caddy renews it by itself).
  `default_sni` is needed because browsers send no server name to a bare IP. Fallback: `TLS_MODE=internal` in `.env`.
- Secrets: `/opt/shipmentlabel/app/.env` (mode 600). Same values as INDIE `~/.secrets/shipmentlabel.env`.
- First boot: `deploy/aws/user-data.sh` (Docker, unattended security upgrades with reboot at 03:30 UTC if needed, swap, log limits).

## Everyday commands (on the server)
```bash
cd /opt/shipmentlabel/app
C="docker compose -f docker-compose.yml -f deploy/aws/docker-compose.aws.yml"
$C ps                                  # status
$C logs -f --tail 100 backend          # logs (also: web, caddy, postgres)
git pull && $C up -d --build           # deploy the latest code of the checked-out branch
bash deploy/aws/run-tests.sh           # backend tests on a separate database (shipmentlabel_test)
```

## Backup (SHIP-8)
- **What:** gzipped database copy (`s3://shipmentlabel-backup-463946129264/db/shipmentlabel-<UTC>.sql.gz`) + every file in the
  label storage (`.../files/`). Incremental: `aws s3 sync` uploads only new or changed files, never deletes in S3.
- **When:** nightly 07:00 UTC (systemd timer) and the **Back up now** button on the app's *Files & Backup* page.
- **Where to see it:** *Files & Backup* page (last result), or `sudo cat /var/lib/docker/volumes/app_label_storage/_data/.backup/status.json`,
  `journalctl -u shipmentlabel-backup`.
- **Install / repair:** `sudo bash deploy/aws/install-backup.sh` (AWS CLI + systemd units). Run by hand: `sudo systemctl start shipmentlabel-backup`.
- **Restore:** `aws s3 sync s3://shipmentlabel-backup-463946129264/files/ <volume>/` and
  `aws s3 cp s3://.../db/<file>.sql.gz - | gunzip | docker compose exec -T postgres psql -U shipmentlabel shipmentlabel`
  (into an empty database). A deleted/overwritten file: pick an older version in the S3 console (kept 90 days).
- **Cost:** about $0.025 per GB-month; well under $0.25/month in year one at 100 labels/day.

## Changing secrets
- **ePost keys:** set `EPG_API_KEY_SANDBOX` / `EPG_API_KEY_PRODUCTION` in `.env`, then `$C up -d backend`.
- **Admin password:** new value (16+ characters) in `.env` and INDIE's `~/.secrets/shipmentlabel.env`, then `$C up -d backend`.
- **Log everyone out:** new `SESSION_SECRET` (32+ characters), then `$C up -d backend`.
- The backend refuses to start with a missing, short or placeholder password/secret (SHIP-4).

## Shutting it down (stops all costs)
Terminate the instance (deletes its disk), release the Elastic IP, delete the security group, key pair, role/instance
profile `shipmentlabel-ec2-ssm` and the budget. Back up the database first if it holds anything needed
(`$C exec postgres pg_dump -U shipmentlabel shipmentlabel > backup.sql`).
