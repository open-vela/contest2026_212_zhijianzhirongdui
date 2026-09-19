#!/usr/bin/env bash
# One-command server deployment for the VelaMesh demo.
#
# Usage:
#   cp .env.example .env   # then edit MQTT_BROKER / credentials
#   ./run.sh
#
# Requires: python3, pip, a running MQTT broker reachable from this host
# (mosquitto on the PC, or the same broker the ESP32 firmware uses).
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and configure MQTT_BROKER first." >&2
  exit 1
fi

# Python venv keeps deps out of the system.
if [ ! -d .venv ]; then
  echo "[setup] creating venv..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[setup] installing deps (cached after first run)..."
pip install -q -r requirements.txt

mkdir -p data

echo "[run] starting server on $(grep -E '^HOST=' .env | cut -d= -f2):$(grep -E '^PORT=' .env | cut -d= -f2)"
echo "[run] login: admin / admin123 (tenant: default)"
echo "[run] docs:  http://<host>:8000/docs"
exec python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
