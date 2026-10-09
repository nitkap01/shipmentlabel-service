#!/bin/bash
# SHIP-6: first boot of the shipmentlabel EC2 server (Ubuntu 24.04 arm64, t4g.large, ap-south-1).
# Docker from Docker's own apt repo + compose plugin, unattended security upgrades, 2 GB swap, Docker log limits.
# No secrets here: the app's .env is copied over SSH afterwards.
set -euxo pipefail
exec > /var/log/shipmentlabel-setup.log 2>&1

export DEBIAN_FRONTEND=noninteractive
hostnamectl set-hostname shipmentlabel

# 2 GB swap (8 GB RAM; Next.js and Docker builds can spike)
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10 && echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
fi

apt-get update
apt-get -y upgrade
apt-get install -y ca-certificates curl git unattended-upgrades

# automatic security updates (reboot at 03:30 UTC only when a kernel update needs it)
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat > /etc/apt/apt.conf.d/52shipmentlabel-reboot <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:30";
EOF

# Docker (official repository)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# keep container logs small
cat > /etc/docker/daemon.json <<'EOF'
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }
EOF
systemctl restart docker
usermod -aG docker ubuntu

mkdir -p /opt/shipmentlabel && chown ubuntu:ubuntu /opt/shipmentlabel
touch /var/log/shipmentlabel-setup.done
