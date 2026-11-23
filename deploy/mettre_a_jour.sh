#!/usr/bin/env bash
# Récupère la dernière version, met la base à jour et redémarre l'outil Prospection.
set -euo pipefail
cd "$(dirname "$0")/.."
bash deploy/sauvegarder.sh
git pull --ff-only
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput -v0
if [ "$(uname)" = "Darwin" ] && launchctl print "gui/$(id -u)/fr.formast.prospection" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/fr.formast.prospection"
  echo "Outil mis à jour et redémarré."
else
  echo "Outil mis à jour. Redémarrez-le : arrêtez-le (Ctrl+C) puis  bash deploy/demarrer.sh"
fi
