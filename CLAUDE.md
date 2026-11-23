# Outil Prospection FORMA'ST — consignes pour Claude Code

- Outil **interne et propriétaire** d'aide à la prospection, **indépendant de FORM'AO**. Ne jamais importer de code de FORM'AO : le seul lien est l'API décrite dans `docs/API_FORMAO.md`, facultative, en lecture seule (`prospection/services/formao.py`).
- Hors périmètre : devis, facturation et trésorerie (outil existant relié à Penny Line) ; planning et charge des formateurs (Planif ST) ; veille des AO (FORM'AO).
- Cahier des charges : `docs/CAHIER_DES_CHARGES.md` (fait foi). Maquette de référence des écrans : `docs/maquette.html`.

## Règles non négociables

- Jamais d'automatisation de LinkedIn : ni lecture de profils, ni envoi d'invitation ou de message. Seules la connexion du compte (OAuth) et la publication de posts validés passent par l'API officielle.
- Opposition globale vérifiée à l'import, à l'ajout d'un contact et à l'envoi ; mention RGPD ajoutée par le code à chaque e-mail.
- L'IA n'invente rien : faits issus de la fiche, du profil et des références citables ; `[À COMPLÉTER : …]` sinon.
- Secrets uniquement dans `.env`. Redirections limitées au site (`_retour_sur`).
- Interface et textes en français, vouvoiement, phrases courtes.

## Développement

- Python 3.12+, Django 5.2, SQLite. `DJANGO_DEBUG=1` en local.
- Tests : `python manage.py test prospection` ; chaque changement vient avec ses tests.
- Les scripts de `deploy/` doivent rester compatibles avec le bash 3.2 de macOS.
