#!/usr/bin/env bash
# Récupère la dernière version, met la base à jour et redémarre Forma Prospect.
set -euo pipefail
cd "$(dirname "$0")/.."
bash deploy/sauvegarder.sh
if [ ! -d .git ]; then
  echo "Ce dossier n'est pas relié au dépôt GitHub (copie sans git) : la mise à jour automatique est impossible."
  echo "Pour le relier, sans toucher à la base ni au .env :"
  echo "  git init -q && git remote add origin https://github.com/forma-st/forma-prospection.git && git fetch -q origin main && git checkout -f -B main origin/main"
  echo "puis :  bash deploy/installer.sh --demarrage-auto"
  exit 1
fi
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
