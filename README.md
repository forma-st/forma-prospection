# Prospection FORMA'ST — outil interne d'aide à la prospection

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
  - « Améliorer avec l'IA » si une clé Anthropic est présente ;
  - contrôle avant envoi noté sur 100, mention RGPD toujours ajoutée ;
  - l'envoi se fait depuis votre messagerie : « J'ai envoyé ce message » l'inscrit dans l'historique et planifie la relance.
- **Import** :
  - fichiers CSV ou Excel, avec correspondance des colonnes ;
  - contrôle de chaque ligne (doublons, SIRET, opposition, e-mails personnels), annulable pendant 30 jours ;
  - acheteurs publics de FORM'AO, si les deux outils sont reliés.
- **Annuaire officiel des entreprises** : SIREN, NAF, effectif, établissements et IDCC, en un clic ou chaque matin.
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
| `manage.py charger_demo_prospection` | Données fictives de démonstration (`--effacer` pour les retirer) |

## Documentation

| Document | Contenu |
|---|---|
| [docs/CAHIER_DES_CHARGES.md](docs/CAHIER_DES_CHARGES.md) | Cahier des charges complet, phasage |
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
    qualite.py          contrôle avant envoi
    journee.py          « Ma journée »
    rgpd.py             opposition, mention d'information
    linkedin.py         option LinkedIn (OAuth, publication, plafonds)
    formao.py           lien facultatif avec FORM'AO
  management/commands/  prospection_quotidienne, charger_demo_prospection
deploy/                 installation interne (Mac / Linux), démarrage, sauvegarde, mise à jour
docs/                   cahier des charges, comparatif, maquette, API FORM'AO, kit d'intégration
```
