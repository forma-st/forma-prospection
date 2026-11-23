#!/usr/bin/env bash
# Toutes les 5 minutes : avance les séquences, envoie la file d'attente, relève les réponses.
set -uo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python manage.py prospection_envois
