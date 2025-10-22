# CoopDoor – full repo bundle (API + UI + scripts + systemd)

This bundle contains everything to stand up the coop door API with a simple web UI,
plus install/uninstall/backup/restore scripts and systemd units.

## Layout
```
api/
  coopdoor_api.py
  schedule_apply.py
ui/
  index.html
  manifest.webmanifest
  icon-192.png
  icon-512.png
  apple-touch-icon.png
  apple-touch-icon-152.png
  apple-touch-icon-167.png
  coopdoor-icon.png
scripts/
  install.sh
  uninstall.sh
  backup.sh
  restore.sh
systemd/
  coopdoor-api.service
  coopdoor-apply-schedule.service
  coopdoor-apply-schedule.timer
```

## Quick start (on the Pi)
```bash
# copy repo to the Pi, then:
cd /path/to/coopdoor-repo
sudo bash scripts/install.sh
# after install:
tailscale serve --bg http://127.0.0.1:8080   # if you want Tailnet HTTPS
```

UI will be at `https://<hostname>.<tailnet>.ts.net/ui/` if served via Tailscale,
or `http://<pi-ip>:8080/ui/` on LAN.

## Backup & Restore
```bash
sudo bash scripts/backup.sh    # writes a tarball to /var/backups/coopdoor-<ts>.tgz
sudo bash scripts/restore.sh /var/backups/coopdoor-<ts>.tgz
```

## Uninstall
```bash
sudo bash scripts/uninstall.sh
```

## Notes
* If you already have a working `coop-door` CLI/daemon, the scripts will NOT overwrite it.
* API auth token is optional. If you want to require a token: `echo 'COOPDOOR_TOKEN=...'
  | sudo tee -a /etc/coopdoor/env && sudo systemctl restart coopdoor-api.service`.
* ZIP→lat/lon geocoding is offline via `pgeocode`. Sunrise/sunset via `astral`.
* The UI settings for Base URL & token are stored in the browser's `localStorage`.
