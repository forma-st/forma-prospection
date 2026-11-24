#!/usr/bin/env bash
# Partage Forma Prospect avec vos collègues par Tailscale (réseau privé : rien n'est exposé sur Internet).
# À lancer sur l'ordinateur ou le serveur où tourne l'outil :   bash deploy/partager_tailscale.sh
# Option :  --http   pour n'utiliser que l'adresse http://100.x.x.x:8010 (sans le certificat HTTPS de Tailscale).
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8010}"
HTTPS_TS=1
[ "${1:-}" = "--http" ] && HTTPS_TS=0

TS="$(command -v tailscale || true)"
[ -z "$TS" ] && [ -x "/Applications/Tailscale.app/Contents/MacOS/Tailscale" ] && TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
if [ -z "$TS" ]; then
  echo "Tailscale n'est pas installé sur cette machine (ou sa commande est introuvable)."
  echo "  Mac : installez l'application Tailscale, connectez-vous, puis relancez ce script."
  echo "  Linux : curl -fsSL https://tailscale.com/install.sh | sh  puis  sudo tailscale up"
  exit 1
fi
if ! "$TS" status >/dev/null 2>&1; then
  echo "Tailscale n'est pas connecté : ouvrez l'application Tailscale (ou  sudo tailscale up), puis relancez."
  exit 1
fi

NOM="$("$TS" status --json | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
IP="$("$TS" ip -4 | head -1)"
echo "==> Machine Tailscale : $NOM ($IP)"

.venv/bin/python - "$NOM" "$IP" "$PORT" <<'PYEOF'
import sys
nom, ip, port = sys.argv[1:4]
lignes = open(".env", encoding="utf-8").read().splitlines()
def ajouter(cle, valeurs):
    for i, l in enumerate(lignes):
        if l.startswith(cle + "="):
            existantes = [v for v in l.split("=", 1)[1].split(",") if v.strip()]
            lignes[i] = f"{cle}=" + ",".join(dict.fromkeys(existantes + valeurs))
            return
    lignes.append(f"{cle}=" + ",".join(valeurs))
ajouter("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1", nom, ip])
ajouter("DJANGO_CSRF_TRUSTED_ORIGINS", [f"https://{nom}", f"http://{nom}:{port}", f"http://{ip}:{port}"])
open(".env", "w", encoding="utf-8").write("\n".join(lignes) + "\n")
PYEOF
chmod 600 .env
echo "    .env complété (adresses Tailscale autorisées)."

URL="http://$IP:$PORT/"
if [ "$HTTPS_TS" = "1" ]; then
  if "$TS" serve --bg "$PORT" >/dev/null 2>&1; then
    URL="https://$NOM/"
    echo "    Adresse sécurisée (HTTPS) activée par Tailscale."
  else
    echo "    HTTPS Tailscale indisponible : activez « MagicDNS » et « HTTPS Certificates » dans la console Tailscale"
    echo "    (login.tailscale.com > DNS), puis relancez. En attendant, l'adresse http ci-dessous fonctionne."
  fi
fi

echo "==> Redémarrage de l'outil"
if [ "$(uname)" = "Darwin" ] && launchctl print "gui/$(id -u)/fr.formast.prospection" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/fr.formast.prospection"
else
  for p in $(lsof -ti "tcp:$PORT" 2>/dev/null || true); do kill "$p" 2>/dev/null || true; done
  sleep 1
  nohup env PORT="$PORT" bash deploy/demarrer.sh >> logs/serveur.log 2>&1 &
fi

echo
echo "Forma Prospect est partagé sur votre réseau Tailscale :"
echo "  $URL"
echo "Pour votre collègue :"
echo "  1. Invitez-le dans votre réseau Tailscale (console Tailscale > Users > Invite) ou partagez-lui cette machine (Share)."
echo "  2. Créez son compte dans Forma Prospect : menu Réglages > Utilisateurs > Ajouter."
echo "  3. Il ouvre l'adresse ci-dessus, Tailscale allumé."
echo "L'outil reste accessible tant que cette machine est allumée et connectée à Tailscale."
