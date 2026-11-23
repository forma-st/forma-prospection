# Installation de l'outil Prospection (Mac ou PC Linux du bureau)

L'outil Prospection est **indépendant de FORM'AO** : sa propre base, ses comptes, son adresse (port 8010 par défaut). Il peut tourner sur le même ordinateur que FORM'AO, et s'y relier si vous le souhaitez (voir [docs/API_FORMAO.md](../docs/API_FORMAO.md)). Compter 10 minutes.

## 1. Prérequis (une seule fois)

Sur Mac, dans le **Terminal** : installez Homebrew (https://brew.sh), puis :

```bash
brew install python@3.12 git
```

Sur Linux (Debian, Ubuntu) :

```bash
sudo apt install python3 python3-venv git
```

## 2. Récupérer l'outil

**Sur Mac, n'installez pas l'outil dans Documents, Bureau, Téléchargements ou iCloud** : macOS interdit au démarrage automatique d'y accéder (« Operation not permitted »). Utilisez votre dossier personnel, par exemple `~/outil-prospection`.

```bash
git clone https://github.com/forma-st/form-prospection.git ~/outil-prospection && cd ~/outil-prospection
```

L'adresse du dépôt est à adapter tant que l'outil n'a pas son dépôt définitif (voir le README).

## 3. Installer

```bash
bash deploy/installer.sh --demarrage-auto
```

Le script installe les dépendances, crée le fichier `.env`, prépare la base (avec un catalogue d'exemple) et vous demande un **identifiant et un mot de passe administrateur**. Avec `--demarrage-auto`, l'outil démarre aussitôt et redémarre à chaque ouverture de session ; le traitement du matin tourne à 7 h 40 (reprises, relances, annuaire, scores, sauvegarde).

- `--demo` : ajoute des prospects **fictifs** pour faire le tour de l'outil. Pour les retirer : `.venv/bin/python manage.py charger_demo_prospection --effacer`.
- Autre port : `PORT=8020 bash deploy/installer.sh --demarrage-auto`.
- Si le pare-feu du Mac le demande, autorisez Python à accepter les connexions entrantes : c'est ce qui permet à l'équipe d'y accéder.

## 4. Utiliser

- Sur l'ordinateur qui héberge l'outil : http://localhost:8010/ (tapez bien `http://` dans Safari).
- Depuis un autre poste du bureau : l'adresse affichée à la fin de l'installation, par exemple `http://192.168.1.20:8010/`.
- Comptes de l'équipe : menu *Utilisateurs* (administrateur).
- Catalogue et profil (utilisés pour le potentiel estimé et la rédaction) : menu *Catalogue et profil*. Remplacez les tarifs d'exemple, ou reprenez-les de FORM'AO.

## 5. Réglages facultatifs (dans `.env`, puis redémarrer)

| Réglage | Effet |
|---|---|
| `ANTHROPIC_API_KEY=sk-ant-…` | Bouton « Améliorer avec l'IA ». Sans clé, les modèles intégrés suffisent |
| `FORMAO_URL=http://localhost:8000` et `FORMAO_JETON=…` | Lien avec FORM'AO : import des acheteurs publics, reprise du profil et du catalogue. FORM'AO doit exposer l'API décrite dans `docs/API_FORMAO.md` |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | Option LinkedIn (à activer aussi dans *Paramètres*). URL de redirection à déclarer : `http://localhost:8010/prospection/linkedin/retour/`, connexion à faire depuis l'ordinateur qui héberge l'outil |

Redémarrer sur Mac :

```bash
launchctl kickstart -k gui/$(id -u)/fr.formast.prospection
```

## 6. Au quotidien

| Besoin | Commande |
|---|---|
| Mettre à jour | `bash deploy/mettre_a_jour.sh` (sauvegarde d'abord, puis redémarre) |
| Sauvegarder maintenant | `bash deploy/sauvegarder.sh` → `sauvegardes/` (30 jours) |
| Démarrer à la main | `bash deploy/demarrer.sh` |
| Journaux | `logs/serveur.log`, `logs/matin.log` |

Copiez régulièrement `sauvegardes/` sur un disque externe ou un partage réseau.

## 7. Si vous aviez installé la version mélangée (`~/outil-ao`, AO + Prospection)

Cette version de test est remplacée par deux outils séparés. Pour reprendre vos prospects dans le nouvel outil :

1. Exportez les données de prospection de l'ancienne installation :

```bash
cd ~/outil-ao && .venv/bin/python manage.py dumpdata prospection --natural-foreign --indent 1 -o ~/prospection-export.json
```

2. Arrêtez et retirez son démarrage automatique :

```bash
launchctl bootout gui/$(id -u)/fr.formast.outil-ao; launchctl bootout gui/$(id -u)/fr.formast.outil-ao.matin; rm -f ~/Library/LaunchAgents/fr.formast.outil-ao*.plist
```

3. Installez le nouvel outil (étapes 2 et 3), **avec le même identifiant administrateur**, puis importez :

```bash
cd ~/outil-prospection && .venv/bin/python manage.py loaddata ~/prospection-export.json
```

4. Vérifiez vos prospects, puis supprimez `~/outil-ao` quand tout est en ordre. FORM'AO s'installe de son côté avec son propre kit.

## Limites

- Joignable seulement quand l'ordinateur est allumé et réveillé (désactivez la mise en veille automatique).
- Accès en `http` sur le réseau du bureau : ne l'ouvrez pas sur Internet. Pour un accès extérieur, il faudra un serveur en HTTPS.
- Base SQLite : adaptée à quelques utilisateurs.
