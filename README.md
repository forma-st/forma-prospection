# Forma Prospect — outil interne d'aide à la prospection de FORMA'ST

Application **indépendante** de FORM'AO (suivi, veille et gestion des appels d'offres). Elle peut s'y relier de façon facultative pour le suivi commercial des acheteurs publics : voir [docs/API_FORMAO.md](docs/API_FORMAO.md).

## Ce que fait l'outil

- **Ma journée** : les prochaines actions classées (tâches en retard, relances de recyclage, prospects A à contacter), avec *Fait* et *Demain*, et un objectif du jour.
- **Prospects et fiche** :
  - score sur 100 (adéquation, intention, accessibilité) et palier A / B / C, avec l'explication en une phrase ;
  - besoin estimé : SST à former, manutention, exercices d'évacuation, potentiel ;
  - signaux sourcés, contacts, guide de découverte, historique ;
  - vues enregistrées, et touches J / K pour passer d'une fiche à l'autre.
- **Rédaction** :
  - e-mail, invitation LinkedIn, script d'appel et relance, avec ton et consigne ;
  - « Améliorer avec l'IA » si une clé Anthropic est présente, avec suivi des coûts, budget mensuel et simulateur (menu *Coûts IA*) ;
  - contrôle avant envoi noté sur 100, mention RGPD toujours ajoutée ;
  - l'envoi se fait depuis votre messagerie : « J'ai envoyé ce message » l'inscrit dans l'historique et planifie la relance.
- **Recherche automatique** (phase 3) : chaque matin, l'outil cherche les entreprises de la cible et les présente « À qualifier » :
  - annuaire officiel des entreprises : activité, départements, effectif minimum et maximum, nombre de sites ;
  - BODACC : nouveaux établissements ;
  - Géorisques : sites industriels classés (ICPE) ;
  - France Travail : offres QSE / HSE (signal « recrutement QSE ») et recrutements en nombre, identifiants gratuits à créer ;
  - dix recherches livrées (France entière, sites industriels, réseaux multi-sites, de 50 à 2 000 salariés) ;
  - priorité du mois affichée selon la saisonnalité. Analyse dans [docs/CIBLAGE.md](docs/CIBLAGE.md).
- **Import** :
  - fichiers CSV ou Excel, avec correspondance des colonnes ;
  - contrôle de chaque ligne (doublons, SIRET, opposition, e-mails personnels), annulable pendant 30 jours ;
  - acheteurs publics de FORM'AO, si les deux outils sont reliés.
- **Annuaire officiel des entreprises** : SIREN, NAF, effectif, établissements et IDCC, en un clic ou chaque matin.
- **Séquences** (phase 2) : e-mails, appels et tâches LinkedIn enchaînés, avec arrêt automatique sur réponse, opposition, rebond ou RDV, et pause en cas d'absence. Quatre séquences sont livrées (ouverture de site, recrutement QSE, réactivation MAC SST, acheteur public).
- **Messagerie** (phase 2) :
  - boîtes d'envoi SMTP et relève IMAP ;
  - file d'envoi avec validation, plafonds par boîte, plages horaires et jours ouvrés ;
  - un message n'est jamais envoyé deux fois ;
  - **mode test activé par défaut** : tout part vers votre adresse de test.
- **Réponses** (phase 2) : tri automatique (intéressé, pas maintenant, mauvais interlocuteur, déjà équipé, absence, opposition, rebond), actions proposées, date de reprise détectée.
- **Statistiques** : entonnoir, taux de réponse, réponses par type, rendement des sources.
- **Historique des formations** : échéances (MAC SST à 24 mois, évacuation à 6 mois…) et relances.
- **Tâches**, **liste d'opposition (RGPD)**, **catalogue et profil**, **paramètres du score**.
- **Option LinkedIn**, désactivée par défaut :
  - connexion du compte et publication de posts par l'API officielle ;
  - invitations préparées, recherches, plafonds de prudence, consignes pour le copilote Claude in Chrome ;
  - l'outil n'envoie jamais d'invitation ni de message à votre place.

Hors périmètre : devis et facturation (outil existant relié à Penny Line), planning des formateurs (Planif ST), veille AO (FORM'AO).

## Installer

Voir [deploy/INSTALLATION.md](deploy/INSTALLATION.md). En résumé, depuis le dossier de l'outil :

```bash
bash deploy/installer.sh --demarrage-auto
```

L'outil est ensuite disponible sur http://localhost:8010/.

## Développer

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
DJANGO_DEBUG=1 .venv/bin/python manage.py migrate && DJANGO_DEBUG=1 .venv/bin/python manage.py runserver 8010
```

```bash
.venv/bin/python manage.py test prospection
```

| Commande | Rôle |
|---|---|
| `manage.py prospection_quotidienne --sirene` | Reprises, relances des formations à échéance, annuaire, scores (chaque matin) |
| `manage.py prospection_recherche` | Recherche automatique de prospects (chaque matin ; `--forcer` ignore les mois actifs) |
| `manage.py prospection_envois` | Séquences, file d'envoi, relève des réponses (toutes les 5 minutes) |
| `manage.py charger_demo_prospection` | Données fictives de démonstration (`--effacer` pour les retirer) |

## Documentation

| Document | Contenu |
|---|---|
| [docs/CAHIER_DES_CHARGES.md](docs/CAHIER_DES_CHARGES.md) | Cahier des charges complet, phasage |
| [docs/CIBLAGE.md](docs/CIBLAGE.md) | Analyse du marché et de la concurrence, cœur de cible, saisonnalité |
| [docs/COMPARATIF.md](docs/COMPARATIF.md) | Comparatif du marché (Koban, HubSpot, Salesforce, Attio…) |
| [docs/maquette.html](docs/maquette.html) | Maquette fonctionnelle (ouvrir dans un navigateur) |
| [docs/API_FORMAO.md](docs/API_FORMAO.md) | Lien facultatif avec FORM'AO |
| [docs/kit-integration/](docs/kit-integration/README.md) | Kit pour intégrer la Prospection dans une autre application (CRM) |

## Architecture

```
config/                 réglages, adresses (connexion, /prospection/, /admin/)
prospection/
  models.py             comptes, contacts, signaux, historique des formations, tâches, opposition,
                        profil et catalogue, paramètres, LinkedIn
  regles.py             segments, signaux, échéances, tranches d'effectif
  services/
    scoring.py          score et besoin estimé
    imports.py          lecture CSV / XLSX, correspondance, dédoublonnage, contrôles
    sirene.py           annuaire officiel des entreprises (API publique gratuite)
    redaction.py        modèles intégrés et IA (facultative)
    couts_ia.py         coûts de l'IA : suivi, budget, simulateur
    qualite.py          contrôle avant envoi
    journee.py          « Ma journée »
    rgpd.py             opposition, mention d'information
    linkedin.py         option LinkedIn (OAuth, publication, plafonds)
    formao.py           lien facultatif avec FORM'AO
  management/commands/  prospection_quotidienne, charger_demo_prospection
deploy/                 installation interne (Mac / Linux), démarrage, sauvegarde, mise à jour
docs/                   cahier des charges, comparatif, maquette, API FORM'AO, kit d'intégration
```
