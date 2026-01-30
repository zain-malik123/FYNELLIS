#!/usr/bin/env bash
set -euo pipefail

# Install the templated service file to /etc/systemd/system and start it.
# Usage: sudo ./install_service.sh
# NOTE: Edit deploy/fynelis.service first to replace REPLACE_USER/REPLACE_GROUP

SERVICE_SRC="$(dirname "$0")/fynelis.service"
if [ ! -f "$SERVICE_SRC" ]; then
  echo "Service file not found: $SERVICE_SRC"
  exit 1
fi

echo "Installing service from $SERVICE_SRC to /etc/systemd/system/fynelis.service"
sudo cp "$SERVICE_SRC" /etc/systemd/system/fynelis.service
sudo chmod 644 /etc/systemd/system/fynelis.service
sudo systemctl daemon-reload
sudo systemctl enable --now fynelis.service
echo "Service installed and started. Tail logs with: sudo journalctl -u fynelis -f"
