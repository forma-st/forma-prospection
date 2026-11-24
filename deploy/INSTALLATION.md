# Installation de Forma Prospect (Mac ou PC Linux du bureau)

Forma Prospect est **indépendant de FORM'AO** : sa propre base, ses comptes, son adresse (port 8010 par défaut). Il peut tourner sur le même ordinateur que FORM'AO, et s'y relier si vous le souhaitez (voir [docs/API_FORMAO.md](../docs/API_FORMAO.md)). Compter 10 minutes.

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
git clone https://github.com/forma-st/forma-prospection.git ~/outil-prospection && cd ~/outil-prospection
```

Le dépôt est privé : connectez-vous d'abord à GitHub (GitHub Desktop, ou `gh auth login`).

## 3. Installer

```bash
bash deploy/installer.sh --demarrage-auto
```

Le script installe les dépendances, crée le fichier `.env`, prépare la base (avec un catalogue d'exemple) et vous demande un **identifiant et un mot de passe administrateur**. Avec `--demarrage-auto`, l'outil démarre aussitôt et redémarre à chaque ouverture de session ; le traitement du matin tourne à 7 h 40 (reprises, relances, annuaire, scores, sauvegarde) et les envois toutes les 5 minutes (séquences, file d'envoi, relève des réponses).

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
| `ANTHROPIC_API_KEY=sk-ant-…` | Bouton « Améliorer avec l'IA ». Sans clé, les modèles intégrés suffisent. Coût suivi dans le menu *Coûts IA* (budget mensuel, simulateur) |
| `FORMAO_URL=http://localhost:8000` et `FORMAO_JETON=…` | Lien avec FORM'AO : import des acheteurs publics, reprise du profil et du catalogue. FORM'AO doit exposer l'API décrite dans `docs/API_FORMAO.md` |
| `FRANCETRAVAIL_CLIENT_ID`, `FRANCETRAVAIL_CLIENT_SECRET` | Recherche automatique dans les offres d'emploi : recrutements QSE / HSE et recrutements en nombre. Voir ci-dessous |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | Option LinkedIn (à activer aussi dans *Paramètres*). URL de redirection à déclarer : `http://localhost:8010/prospection/linkedin/retour/`, connexion à faire depuis l'ordinateur qui héberge l'outil |

**Obtenir les identifiants France Travail** (gratuit, 10 minutes) :
1. Créez un compte sur https://francetravail.io (espace développeurs), puis une **application**.
2. Abonnez l'application à l'API **« Offres d'emploi v2 »**.
3. Copiez l'**identifiant client** et la **clé secrète** dans `.env` (`FRANCETRAVAIL_CLIENT_ID`, `FRANCETRAVAIL_CLIENT_SECRET`), puis redémarrez.
4. Dans *Recherche automatique*, cliquez sur « Lancer » sur « Recrutements QSE / HSE » pour vérifier.

Redémarrer sur Mac :

```bash
launchctl kickstart -k gui/$(id -u)/fr.formast.prospection
```

## 6. Messagerie (phase 2)

Dans **Messagerie** :
1. Ajoutez une **boîte d'envoi** (serveur SMTP, identifiant, mot de passe ; serveur IMAP pour relever les réponses), puis cliquez sur **Tester**.
2. Laissez le **mode test** activé et renseignez votre adresse de test : tous les e-mails vous arrivent, avec le vrai destinataire dans l'objet.
3. Inscrivez quelques prospects dans une **séquence** (depuis leur fiche ou en les cochant dans la liste). Les e-mails préparés apparaissent dans *Messagerie → À valider*.
4. Quand tout vous convient, décochez le mode test.

Pour Microsoft 365, l'envoi SMTP authentifié doit être autorisé sur la boîte (centre d'administration Exchange) ; la connexion directe Microsoft (Graph) est prévue ensuite.

## 7. Au quotidien

| Besoin | Commande |
|---|---|
| Mettre à jour | `bash deploy/mettre_a_jour.sh` (sauvegarde d'abord, puis redémarre) |
| Sauvegarder maintenant | `bash deploy/sauvegarder.sh` → `sauvegardes/` (30 jours) |
| Démarrer à la main | `bash deploy/demarrer.sh` |
| Journaux | `logs/serveur.log`, `logs/matin.log`, `logs/envois.log` |

Copiez régulièrement `sauvegardes/` sur un disque externe ou un partage réseau.

## 8. Si vous aviez installé la version mélangée (`~/outil-ao`, AO + Prospection)

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


## France Travail : la connexion est refusée (400)

Le message affiché donne la cause renvoyée par France Travail :

- **invalid_client** : identifiant ou clé secrète erronés. Recopiez-les depuis *Mes applications* sur francetravail.io, sans espace ni guillemet, ou régénérez la clé secrète.
- **invalid_scope** : l'application n'a pas accès à l'API « Offres d'emploi v2 ». Ouvrez l'application dans *Mes applications* et regardez la liste de ses API. Le catalogue « Ajouter » ne montre que les API **pas encore** ajoutées : si « Offres d'emploi » n'y figure pas, elle est sans doute déjà rattachée.

Après avoir corrigé le `.env`, relancez l'outil (`bash deploy/mettre_a_jour.sh` le fait), puis cliquez sur *Lancer* devant une recherche France Travail.

## Coûts IA

Le menu *Réglages > Coûts IA* affiche la dépense du mois (estimée d'après les jetons consommés), la projection de fin de mois et le budget. Une alerte apparaît dans *Ma journée* à partir de 80 % du budget. Par défaut, l'IA est suspendue une fois le budget atteint : les modèles intégrés prennent le relais. Le simulateur estime le coût mensuel selon les volumes prévus et compare les modèles. Les tarifs sont dans `prospection/services/couts_ia.py`. La facture Anthropic fait foi.

## La Bonne Boîte (France Travail)

Avec les mêmes identifiants France Travail, la source « La Bonne Boîte » trouve les entreprises qui devraient recruter dans les 6 mois sur un métier donné (codes ROME). Votre application doit être abonnée à l'API « La Bonne Boîte v2 ». Trois recherches sont livrées : logistique, industrie, santé et médico-social. En France entière, elles parcourent huit départements par nuit.

Pour vérifier les droits de l'application : `.venv/bin/python manage.py prospection_diagnostic_ft`. Une recherche « offres d'emploi » dont l'API n'est pas accessible se désactive d'elle-même, avec l'explication dans le journal.

## Coordonnées des prospects

Le bouton « Chercher les coordonnées » d'une fiche, et chaque matin les 30 meilleurs prospects sans standard, passent par :

1. l'annuaire officiel : adresse du siège, président, directeur général ou gérant (données publiques du registre) ;
2. le site de l'entreprise (celui de la fiche, le domaine des e-mails connus, ou un domaine deviné et retenu seulement si le site cite le SIREN ou le nom) : téléphone du standard et e-mail générique (contact@, accueil@…) sur l'accueil, la page contact et les mentions légales ;
3. en option, Google Places pour le standard quand le site n'en donne pas : renseignez `GOOGLE_PLACES_API_KEY=` dans le `.env` (clé de l'API « Places API (New) » sur la console Google Cloud ; un quota gratuit mensuel couvre largement 30 recherches par jour).

Seules des coordonnées génériques sont prises sur le web : jamais d'e-mail nominatif. Rien de ce qui est déjà saisi n'est écrasé. Pour lancer à la main : `.venv/bin/python manage.py prospection_coordonnees --max 30`, ou `--id 12` pour une fiche.
