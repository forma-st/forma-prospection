#!/usr/bin/env bash
# Démarre Forma Prospect (gunicorn), accessible depuis le réseau local. Ctrl+C pour arrêter.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8010}"
echo "Forma Prospect : http://localhost:$PORT/  (Ctrl+C pour arrêter)"
exec .venv/bin/gunicorn config.wsgi --bind "0.0.0.0:$PORT" --workers 1 --threads 4 --timeout 120
