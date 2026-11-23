#!/usr/bin/env bash
# Recherche automatique de prospects, puis reprises, relances des formations à échéance, annuaire, scores ; puis sauvegarde.
set -uo pipefail
cd "$(dirname "$0")/.."
echo "=== $(date '+%d/%m/%Y %H:%M') ==="
.venv/bin/python manage.py prospection_recherche || echo "Recherche automatique : erreur (voir ci-dessus)"
.venv/bin/python manage.py prospection_quotidienne --sirene || echo "Prospection : erreur (voir ci-dessus)"
bash deploy/sauvegarder.sh
