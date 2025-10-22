#!/usr/bin/env bash
set -euo pipefail

echo "==> Stopping services"
sudo systemctl disable --now coopdoor-apply-schedule.timer || true
sudo systemctl disable --now coopdoor-api.service || true

echo "==> Removing systemd units"
sudo rm -f /etc/systemd/system/coopdoor-api.service
sudo rm -f /etc/systemd/system/coopdoor-apply-schedule.service
sudo rm -f /etc/systemd/system/coopdoor-apply-schedule.timer
sudo systemctl daemon-reload

echo "==> Removing sudoers rule"
sudo rm -f /etc/sudoers.d/coopdoor-apply || true

read -r -p "Remove /opt/coopdoor (y/N)? " ans
if [[ "${ans:-N}" =~ ^[Yy]$ ]]; then
  sudo rm -rf /opt/coopdoor
fi
echo "==> Uninstall complete."
