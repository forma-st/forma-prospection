# Kit d'intégration — Agent d'aide à la prospection FORMA'ST

Version du 20/11/2026, cahier des charges v0.6. Tout ce qu'il faut pour développer l'agent dans une autre application (CRM interne ou application dédiée) avec une autre session Claude Code.

## Démarrage en 3 étapes

1. Copier ce dossier `agent-prospection/` dans le dépôt cible (par exemple `docs/agent-prospection/`).
2. Copier `CLAUDE.md` à la racine du dépôt cible, ou le fusionner avec celui qui existe.
3. Ouvrir une session Claude Code sur ce dépôt et coller le message de [`PROMPT_DEMARRAGE.md`](PROMPT_DEMARRAGE.md).

## Contenu

| Chemin | Contenu | Pour qui |
|---|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Contexte, écosystème, règles non négociables, conventions | Claude Code |
| [`PROMPT_DEMARRAGE.md`](PROMPT_DEMARRAGE.md) | Message à coller dans la nouvelle session | Vous |
| [`docs/SPEC_PROSPECTION.md`](docs/SPEC_PROSPECTION.md) | Cahier des charges complet (fait foi) | Tous |
| [`docs/BENCHMARK_PROSPECTION.md`](docs/BENCHMARK_PROSPECTION.md) | Comparatif du marché et idées retenues | Décision |
| [`docs/PLAN_IMPLEMENTATION.md`](docs/PLAN_IMPLEMENTATION.md) | Lots P1 à P4, critères d'acceptation, tests | Développement |
| [`contrats/API.md`](contrats/API.md) | API attendues du CRM et de l'outil AO, API de l'agent, webhooks signés, Planif ST | Développement CRM et agent |
| [`modele/schema.sql`](modele/schema.sql) | Modèle de données de référence (PostgreSQL) | Développement |
| [`regles/regles_metier.json`](regles/regles_metier.json) | Segments, signaux, score, besoin, échéances, envoi, contrôle avant envoi, RGPD | Développement, paramétrage |
| [`regles/sequences.json`](regles/sequences.json) · [`automatisations.json`](regles/automatisations.json) · [`campagnes.json`](regles/campagnes.json) | Contenus livrés par défaut | Paramétrage |
| [`ia/PROMPTS.md`](ia/PROMPTS.md) | Prompts, schémas de sortie, outils de l'assistant | Développement |
| [`maquette/prospection.html`](maquette/prospection.html) | Maquette fonctionnelle autonome (double-clic pour l'ouvrir) | Tous |
| [`donnees/`](donnees/) | Données fictives, fichier d'import d'exemple, modèle d'import de l'historique | Tests |
| [`code_reutilisable/`](code_reutilisable/) | Client HTTP, normalisation, recherche SIRENE issus de l'outil AO | Développement |

## Code de référence

Une première version fonctionnelle (P1 + option LinkedIn) existe dans le dépôt `forma-st/forma-prospection`, dossier `prospection/` (application Django, avec ses tests). L'autre session Claude Code peut s'en inspirer ou la reprendre : modèles, calcul du score et du besoin, import, annuaire, rédaction, contrôle avant envoi, connexion LinkedIn (OAuth) et publication.

## Périmètre en une phrase

Outil interne et propriétaire qui trouve les entreprises ayant un besoin réel en formation santé-sécurité (signaux publics, bases fournies, historique clients), calcule ce besoin, priorise, rédige et aide à contacter dans le respect du RGPD, puis transmet les rendez-vous qualifiés au CRM. **Hors périmètre** : devis et facturation (outil relié à Penny Line), planning et charge des formateurs (Planif ST).

## Questions encore ouvertes

Voir le cahier des charges §11 : technologie et API du CRM, emplacement final de l'agent, bases fournies, historique existant, segments prioritaires, budget d'enrichissement, validation juridique.

Source : dépôt `forma-st/forma-prospection`, dossier `docs/kit-integration/`.
