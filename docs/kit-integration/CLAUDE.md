# Agent de prospection FORMA'ST — consignes pour Claude Code

À copier dans le dépôt de l'application cible (à la racine, ou dans le dossier du module sous le nom `CLAUDE.md`).

## Contexte

- FORMA'ST : organisme de formation en santé et sécurité au travail (SST, MAC SST, incendie et évacuation, UMFI, gestes et postures, QVT / RPS), Qualiopi, habilité INRS SST, siège à Méry-sur-Oise, interventions nationales.
- Le module est un **outil interne et propriétaire d'aide à la prospection**, pour 2 à 5 utilisateurs. Il n'est pas commercialisé.
- Écosystème interne, applications **séparées** :
  - **CRM interne** : clients, contacts, opportunités, formations réalisées ;
  - **outil AO** (Veille AO) : profil, catalogue, références, avis de marchés, attributions ;
  - **outil de facturation** relié à Penny Line : **hors périmètre, aucun accès** ;
  - **Planif ST** et l'optimiseur de tournées : planning et charge des formateurs, **hors périmètre** (lecture seule des sessions, en option, à partir de P2).

## Documents de référence (chemins relatifs au dossier du kit)

1. `docs/SPEC_PROSPECTION.md` : cahier des charges complet (v0.6). **Fait foi.**
2. `docs/PLAN_IMPLEMENTATION.md` : lots et critères d'acceptation.
3. `contrats/API.md` : contrats CRM, outil AO, agent, webhooks.
4. `modele/schema.sql` : modèle de données de référence.
5. `regles/*.json` : règles métier, séquences, automatisations, campagnes.
6. `ia/PROMPTS.md` : prompts et sorties structurées.
7. `maquette/prospection.html` : maquette fonctionnelle (s'ouvre dans un navigateur) ; référence pour les écrans et les comportements.

## Règles non négociables

- **Ne jamais automatiser LinkedIn** (ni collecte, ni envoi). Seuls les textes sont préparés, l'utilisateur envoie lui-même.
- **Opposition globale** : vérifiée à chaque import, chaque rédaction et chaque envoi, sur tous les canaux ; synchronisée avec le CRM.
- **Pied de page RGPD** et lien d'opposition ajoutés par le code à chaque e-mail, jamais supprimables.
- **L'IA n'invente rien** : faits sourcés, `[À COMPLÉTER : …]` sinon. Sorties IA validées par schéma.
- **Aucun devis, aucune facture, aucune trésorerie** dans ce module.
- **Mode test de la messagerie actif par défaut** en développement : aucun e-mail ne part à l'extérieur.
- Pas d'envoi sans plafond, hors plages horaires ou hors jours ouvrés.
- Pas de suivi d'ouverture par pixel (désactivé tant que non validé juridiquement).
- Secrets uniquement dans `.env` ; jetons d'API distincts par application ; webhooks signés HMAC.
- SIREN comme clé commune ; ne jamais dupliquer un client existant du CRM.

## Conventions

- Interface et textes en **français**, vouvoiement, phrases courtes ; nommer les choses comme l'utilisateur les connaît.
- Dates affichées `JJ/MM/AAAA`, fuseau Europe/Paris ; montants `12 345 €`.
- Données de test : uniquement les données fictives du kit (domaines `.example`).
- Chaque lot livré avec ses tests ; un lot n'est terminé que si ses critères d'acceptation passent.
- Démarrer en mode `PROSPECTION_CRM = "autonome"` ; toute lecture / écriture CRM passe par l'interface `PasserelleCRM` (cahier §3.14.1), toute lecture de l'outil AO par `PasserelleAO`.
