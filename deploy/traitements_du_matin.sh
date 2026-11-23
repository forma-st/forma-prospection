#!/usr/bin/env bash
# Prospection : reprises, relances des formations à échéance, annuaire, scores ; puis sauvegarde.
set -uo pipefail
cd "$(dirname "$0")/.."
echo "=== $(date '+%d/%m/%Y %H:%M') ==="
.venv/bin/python manage.py prospection_quotidienne --sirene || echo "Prospection : erreur (voir ci-dessus)"
bash deploy/sauvegarder.sh
