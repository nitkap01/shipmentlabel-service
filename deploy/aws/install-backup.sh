#!/bin/bash
# SHIP-8: install the S3 backup on the server (idempotent). Run once as root:  sudo bash deploy/aws/install-backup.sh
#   - AWS CLI v2 (arm64) if missing
#   - systemd: shipmentlabel-backup.service (runs backup.sh), .timer (nightly 07:00 UTC = 02:00/03:00 New York),
#     .path (the app's "Back up now" button drops .backup/request into the label volume)
set -euo pipefail
APP=/opt/shipmentlabel/app
if ! command -v aws >/dev/null; then
  apt-get install -y unzip >/dev/null
  tmp=$(mktemp -d); cd "$tmp"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o awscliv2.zip
  unzip -q awscliv2.zip && ./aws/install
  cd / && rm -rf "$tmp"
fi
VOL=$(docker volume inspect -f '{{.Mountpoint}}' app_label_storage)
mkdir -p "$VOL/.backup"
chmod +x "$APP/deploy/aws/backup.sh"

cat > /etc/systemd/system/shipmentlabel-backup.service <<EOF
[Unit]
Description=shipmentlabel incremental backup to S3 (SHIP-8)
After=docker.service
[Service]
Type=oneshot
ExecStart=$APP/deploy/aws/backup.sh
EOF
cat > /etc/systemd/system/shipmentlabel-backup.timer <<'EOF'
[Unit]
Description=Nightly shipmentlabel backup to S3
[Timer]
OnCalendar=*-*-* 07:00:00 UTC
Persistent=true
RandomizedDelaySec=300
[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/shipmentlabel-backup.path <<EOF
[Unit]
Description=Run the shipmentlabel backup when the app asks for one
[Path]
PathExists=$VOL/.backup/request
Unit=shipmentlabel-backup.service
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now shipmentlabel-backup.timer shipmentlabel-backup.path
systemctl list-timers shipmentlabel-backup.timer --no-pager | head -3
aws --version
