#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/coopdoor"
VENV="$APP_DIR/.venv"

echo "==> Installing OS deps"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv curl

echo "==> Creating app layout at $APP_DIR"
sudo mkdir -p "$APP_DIR/ui"
sudo chown -R coop:coop "$APP_DIR"

echo "==> Python venv + packages"
if [ ! -x "$VENV/bin/python3" ]; then
  sudo -u coop python3 -m venv "$VENV"
fi
sudo -u coop "$VENV/bin/pip" install --upgrade pip >/dev/null
sudo -u coop "$VENV/bin/pip" install fastapi 'uvicorn[standard]' astral pgeocode >/dev/null

echo "==> Installing API and UI"
sudo install -m 0644 api/coopdoor_api.py "$APP_DIR/coopdoor_api.py"
sudo install -m 0644 api/schedule_apply.py "$APP_DIR/schedule_apply.py"
sudo install -m 0644 ui/index.html "$APP_DIR/ui/index.html"
sudo install -m 0644 ui/manifest.webmanifest "$APP_DIR/ui/manifest.webmanifest"
for f in ui/*.png; do sudo install -m 0644 "$f" "$APP_DIR/ui/"; done

echo "==> Ensure last_event.json exists and writeable"
sudo touch "$APP_DIR/last_event.json"
sudo chown coop:coop "$APP_DIR/last_event.json"
sudo chmod 664 "$APP_DIR/last_event.json"

echo "==> Installing systemd units"
sudo install -m 0644 systemd/coopdoor-api.service /etc/systemd/system/coopdoor-api.service
sudo install -m 0644 systemd/coopdoor-apply-schedule.service /etc/systemd/system/coopdoor-apply-schedule.service
sudo install -m 0644 systemd/coopdoor-apply-schedule.timer /etc/systemd/system/coopdoor-apply-schedule.timer

echo "==> Allow coop to start apply service without password"
sudo bash -c 'cat > /etc/sudoers.d/coopdoor-apply <<EOF
coop ALL=(root) NOPASSWD: /bin/systemctl start coopdoor-apply-schedule.service
EOF'
sudo chmod 0440 /etc/sudoers.d/coopdoor-apply
sudo visudo -cf /etc/sudoers.d/coopdoor-apply >/dev/null

echo "==> Reloading systemd and starting services"
sudo systemctl daemon-reload
sudo systemctl enable --now coopdoor-api.service
sudo systemctl enable --now coopdoor-apply-schedule.timer

echo "==> Done. Visit http://<pi-ip>:8080/ui/ or your Tailnet URL."
