#!/usr/bin/env bash
set -euo pipefail
ts=$(date +%Y%m%d-%H%M%S)
dst="/var/backups/coopdoor-${ts}.tgz"
sudo mkdir -p /var/backups
sudo tar -czf "$dst" \
  /etc/coopdoor \
  /etc/systemd/system/coopdoor-api.service \
  /etc/systemd/system/coopdoor-apply-schedule.service \
  /etc/systemd/system/coopdoor-apply-schedule.timer \
  /opt/coopdoor
echo "$dst"
