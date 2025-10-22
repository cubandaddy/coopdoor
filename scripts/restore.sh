#!/usr/bin/env bash
set -euo pipefail
if [ $# -lt 1 ]; then
  echo "Usage: $0 /path/to/backup.tgz" >&2
  exit 1
fi
src="$1"
echo "==> Restoring from $src"
sudo tar -xzf "$src" -C /
echo "==> Reloading systemd"
sudo systemctl daemon-reload
sudo systemctl enable --now coopdoor-api.service
sudo systemctl enable --now coopdoor-apply-schedule.timer
echo "==> Restore complete."
