# Message à coller dans la nouvelle session Claude Code

Copiez d'abord le dossier `agent-prospection/` dans le dépôt de l'application cible (par exemple sous `docs/agent-prospection/`), poussez-le, puis ouvrez une session Claude Code sur ce dépôt et collez le message ci-dessous. Adaptez le chemin si besoin.

---

```
Nouveau module à intégrer : l'agent d'aide à la prospection de FORMA'ST.
Tout le dossier de conception est dans docs/agent-prospection/ :
- CLAUDE.md : contexte et règles non négociables (à lire en premier) ;
- docs/SPEC_PROSPECTION.md : cahier des charges v0.6, qui fait foi ;
- docs/PLAN_IMPLEMENTATION.md : lots et critères d'acceptation ;
- contrats/API.md : API attendues du CRM et de l'outil AO, API de l'agent, webhooks ;
- modele/schema.sql : modèle de données de référence (PostgreSQL) ;
- regles/*.json : règles métier, séquences, automatisations, campagnes ;
- ia/PROMPTS.md : prompts et schémas de sortie ;
- maquette/prospection.html : maquette fonctionnelle (référence des écrans) ;
- donnees/ : données fictives et modèles de fichiers d'import ;
- code_reutilisable/ : client HTTP, normalisation et recherche SIRENE issus de l'outil AO.

Travail demandé :
1. Lis CLAUDE.md, le cahier des charges et le plan, puis explore ce dépôt.
2. Dis-moi comment le module s'insère dans l'architecture existante : où le placer, ce qui est
   réutilisable ici (authentification, utilisateurs, envoi d'e-mails, tâches de fond, IA),
   les écarts avec le modèle de données de référence, et les questions bloquantes.
   N'écris pas de code à cette étape.
3. Après ma validation, réalise le lot 1.1 (socle) puis les lots suivants de P1, un par un,
   chacun avec ses tests et ses critères d'acceptation, en mode PROSPECTION_CRM = "autonome"
   et avec la messagerie en mode test.

Règles : outil interne et propriétaire ; aucune facturation ni devis (outil existant relié à
Penny Line) ; aucune gestion de la charge formateurs (Planif ST) ; jamais d'automatisation LinkedIn ;
opposition globale vérifiée partout ; interface en français.
```

---

## Si l'application cible est le CRM

Ajoutez au message : « L'agent vivra dans ce CRM : la passerelle CRM peut lire et écrire directement les modèles du CRM au lieu de passer par l'API (cahier §3.14.2, emplacement cible). Garde quand même l'interface `PasserelleCRM` pour pouvoir tester en mode autonome. »

## Si l'application cible est une nouvelle application dédiée

Ajoutez : « Crée l'application en Python 3.12 et Django 5.2, comme l'outil AO, avec PostgreSQL. Les échanges avec le CRM et l'outil AO passent par les API de contrats/API.md. »
