#!/usr/bin/env bash
# Démarre l'outil Prospection (gunicorn), accessible depuis le réseau local. Ctrl+C pour arrêter.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8010}"
echo "Prospection FORMA'ST : http://localhost:$PORT/  (Ctrl+C pour arrêter)"
exec .venv/bin/gunicorn config.wsgi --bind "0.0.0.0:$PORT" --workers 1 --threads 4 --timeout 120
