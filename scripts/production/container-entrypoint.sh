#!/usr/bin/env bash

set -Eeuo pipefail

cd /app

if [[ ! -r /app/.env ]]; then
  printf '[fatal] /app/.env is not mounted; refusing to start\n' >&2
  exit 78
fi

backend/.venv/bin/python scripts/setup-backend-runtime.py --check-only
backend/.venv/bin/python scripts/check-startup-config.py

exec "$@"
