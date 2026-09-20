#!/usr/bin/env bash
# One-command server deployment for the VelaMesh demo.
#
# Usage:
#   ./run.sh                      # zero-config demo start
#
#   Optional: copy the env template and point at a real EMQX/mosquitto
#   broker shared with the ESP32 firmware:
#     cp .env.example .env        # then edit MQTT_BROKER / credentials
#
# Requires: python3, pip. No external MQTT broker required: with
# MQTT_MODE=auto (default) the server probes MQTT_BROKER:MQTT_PORT and, when
# nothing is listening, starts its in-process demo broker on
# 127.0.0.1:${MQTT_EMBEDDED_PORT:-11883}. Point the simulator at it:
#   python scripts/simulate_edge.py --port 11883 --scenario allow
set -euo pipefail

cd "$(dirname "$0")"

# A fresh checkout has no .env: seed it from the template so the documented
# knobs exist; the server also runs fine on built-in defaults.
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "[setup] created .env from .env.example (defaults: embedded broker fallback)"
  else
    echo "[setup] no .env/.env.example; continuing on built-in defaults"
  fi
fi

# Python venv keeps deps out of the system.
PYTHON=python3
if ! command -v python3 >/dev/null 2>&1; then
  PYTHON=python
fi
if [ ! -d .venv ]; then
  echo "[setup] creating venv..."
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[setup] installing deps (cached after first run)..."
pip install -q -r requirements.txt

mkdir -p data logs

# shellcheck disable=SC1091
set -a; [ -f .env ] && . ./.env || true; set +a
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "[run] starting server on ${HOST}:${PORT}"
echo "[run] MQTT_MODE=${MQTT_MODE:-auto} (embedded fallback on 127.0.0.1:${MQTT_EMBEDDED_PORT:-11883} if no broker is reachable)"
echo "[run] login: admin / admin123 (tenant: default)"
echo "[run] docs:  http://127.0.0.1:${PORT}/docs"
exec python -m uvicorn app.main:create_app --factory --host "$HOST" --port "$PORT"
