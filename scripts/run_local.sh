#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  echo "Set up .env using scripts/setup_local.py before starting the app."
  exit 1
fi
docker compose --env-file .env -f infra/compose.yaml -p parkinsense_pk up -d --wait db
uv run python scripts/secure_media_server.py &
media_pid=$!
cleanup() { kill "$media_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
uv run streamlit run app/Home.py --server.address 127.0.0.1
