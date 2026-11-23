#!/usr/bin/env bash
# Sauvegarde la base et les fichiers déposés dans sauvegardes/ (30 jours conservés).
# Copiez ce dossier ailleurs de temps en temps (disque externe, partage réseau).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p sauvegardes
JOUR="$(date +%F)"
.venv/bin/python - "$JOUR" <<'PYEOF'
import sqlite3, sys
src = sqlite3.connect("db.sqlite3"); dst = sqlite3.connect(f"sauvegardes/db-{sys.argv[1]}.sqlite3")
src.backup(dst); dst.close(); src.close()
PYEOF
find sauvegardes -type f -mtime +30 -delete
echo "Sauvegarde du $JOUR faite dans sauvegardes/."
