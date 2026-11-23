# Agent de prospection — Comparatif des outils du marché (novembre 2026)

But : situer l'agent FORMA'ST face aux outils du marché, reprendre leurs meilleures idées et éviter leurs défauts. Complète le [cahier des charges](SPEC_PROSPECTION.md) (§3.18 : améliorations retenues).

> Les fonctions et les prix viennent de sources publiques consultées le 19/11/2026 : pages des éditeurs et comparatifs tiers (liste en fin de document). Les tarifs changent souvent et sont à revérifier avant toute décision.

---

## 1. Les outils comparés

| Outil | Type | Ce qu'il fait le mieux | Limites pour FORMA'ST | Prix indicatif |
|---|---|---|---|---|
| **Koban** (FR) | CRM + marketing automation + gestion commerciale pour PME | Scénarios automatisés (parcours e-mail / SMS selon le comportement), **lead scoring**, suivi des visiteurs du site, segmentation dynamique, relances de devis, hébergement français | Outil généraliste : aucun calcul de besoin réglementaire, pas de signaux publics (BODACC, offres d'emploi, DECP), pas de lien avec les AO ; marketing automation réservé à l'offre haute | ≈ 65 € / utilisateur / mois (offre Business, avec marketing automation) |
| **Neocamino** (FR) | Marketing et commercial « clé en main » pour TPE / PME | **Plan d'actions guidé** pour des dirigeants non spécialistes, suggestions de contenus, newsletters, capture de contacts, accompagnement par des conseillers | Peu d'IA, ciblage sortant limité, pas de données entreprises, pas de séquences multicanales fines | À partir d'≈ 129 € / mois selon un comparatif (tarif « sur demande » ailleurs) |
| **Salesforce** (Sales Cloud, Agentforce Sales) | CRM grand compte + agents IA | **Liste de comptes priorisée chaque matin**, signaux (engagement, offres d'emploi, intention), agent de prospection configurable (critères, sources), **agent SDR** qui relance, qualifie, prend des RDV et passe la main au commercial au bon moment, avec une adresse d'envoi dédiée | Coût et complexité disproportionnés pour 2 à 5 utilisateurs ; données et signaux surtout anglo-saxons ; intégrateur souvent nécessaire | Non publié pour l'agent ; Sales Cloud Enterprise et options IA élevés |
| **HubSpot Sales Hub** (Breeze) | CRM + espace de vente + agents IA | **Espace de vente** unique (tâches, séquences, prochaines étapes), agent de prospection qui surveille les signaux, trouve les contacts et rédige, **score prédictif des affaires**, préparation et suivi des réunions, comptes cibles | Agent pensé d'abord pour l'anglais ; facturation à l'usage (crédits) ; séquences et agents réservés aux offres Professional et plus | Offre Professional requise ; agent facturé en crédits (≈ 1 $ par lead selon une page) |
| **Pipedrive** | CRM simple orienté pipeline | **Pipeline visuel en colonnes** très lisible, activités planifiées, adoption rapide | Prospection sortante et signaux faibles ; IA générique | ≈ 15 à 100 € / utilisateur / mois selon l'offre |
| **Sellsy, Axonaut** (FR) | CRM + devis + facturation pour TPE / PME | **Du devis à la facture** dans le même outil, relances de paiement | Prospection basique ; pas d'IA de ciblage | Quelques dizaines d'euros / utilisateur / mois |
| **lemlist, La Growth Machine** (FR) | Prospection multicanale | Séquences e-mail + LinkedIn + appels, personnalisation avancée (images, vidéos), **tests A/B**, réchauffement des boîtes | **Automatisation de LinkedIn** (risque de fermeture de compte et contraire aux CGU) ; volumes qui abîment la réputation du domaine ; aucune connaissance métier | ≈ 60 à 70 € / identité ou utilisateur / mois |
| **Pappers, Société.com** (FR) | Données légales d'entreprises | Dirigeants, **bilans et chiffre d'affaires**, actes, alertes ; API ; « siretisation » d'un fichier | Pas d'e-mails ni de téléphones ; payant au volume | API payante au volume |
| **Dropcontact, Kaspr, Lusha** | Enrichissement de contacts | E-mails et téléphones professionnels | Conformité très variable : Kaspr a été sanctionné par la CNIL (240 000 €, 2024) ; préférer un service qui calcule et vérifie sans revendre de base | ≈ 0,05 à 0,50 € / contact |
| **Ringover, Aircall, Modjo** (FR) | Téléphonie et analyse d'appels | Appel en un clic, **enchaînement d'appels**, enregistrement, **résumé et points clés par l'IA** | Coût par utilisateur ; enregistrement soumis à information et consentement | ≈ 20 à 60 € / utilisateur / mois |

---

## 2. Ce que l'agent FORMA'ST fait que les autres ne font pas

1. **Le besoin réglementaire est calculé** : nombre de SST à former, recyclages à 24 mois, exercices tous les 6 mois, manutention. Aucun CRM généraliste ne sait dire à un prospect « il vous faut 29 SST ».
2. **L'historique des formations alimente la réactivation** : relances MAC SST et exercices à date, la source de chiffre d'affaires la plus rentable.
3. **Les signaux publics français sont gratuits** : BODACC, SIRENE, France Travail, Géorisques (ICPE), DECP, et les acheteurs et attributions déjà collectés par l'outil AO.
4. **Un seul outil pour les marchés publics et privés**, avec le radar des marchés à renouveler.
5. **RGPD par construction** : opposition globale, information au premier contact, purge à 3 ans, pas d'automatisation LinkedIn.
6. **Coût** : 15 à 30 € par mois d'IA pour toute l'équipe, contre 60 à 150 € par utilisateur et par mois pour les outils du marché.

---

## 3. Idées reprises et intégrées

| # | Idée | Inspirée de | Intégration dans l'agent | Maquette | Phase |
|---|---|---|---|---|---|
| 1 | **« Ma journée »** : liste priorisée des prochaines actions, chacune avec sa raison et son bouton | Salesforce (liste priorisée), HubSpot (espace de vente) | Écran d'accueil : réponses chaudes, retards, échéances clients, prospects A ; actions « Fait » et « Demain » ; objectif du jour | ✅ | P1 |
| 2 | **Compte rendu de la nuit** | Agents Salesforce et HubSpot | « Cette nuit, l'agent a… » : signaux lus, fiches rafraîchies, brouillons, réponses triées | ✅ | P2 |
| 3 | **Pilote automatique par activité** (manuel / propose / automatique), avec budget et plafond | Agentforce SDR (réglage des relances, horaires, boîte dédiée) | Écran de réglage + journal ; LinkedIn bloqué en manuel ; retour automatique en « propose » au-delà du budget | ✅ | P2 |
| 4 | **Passage de main** au commercial au bon moment | Agentforce SDR | Réponse « intéressé » → arrêt de la séquence, notification immédiate, 3 créneaux proposés, fiche de préparation | ✅ (Réponses) | P2 |
| 5 | **Pipeline en colonnes** avec glisser-déposer | Pipedrive | Vue « Colonnes » des prospects par statut | ✅ | P1 |
| 6 | **Vues enregistrées** | HubSpot, Salesforce | Palier A, Avec signal, Sans contact, Acheteurs publics, Clients | ✅ | P1 |
| 7 | **Recherche et commandes rapides** (Ctrl+K), navigation au clavier | Outils de vente modernes | Palette : prospects, écrans, actions ; J / K pour passer d'une fiche à l'autre | ✅ | P1 |
| 8 | **Contrôle de qualité avant envoi** | lemlist, assistants d'écriture commerciale | Longueur, personnalisation, accroche sur le signal, une seule question, mots anti-spam, lien d'opposition, champs à compléter ; note sur 100 | ✅ | P1 |
| 9 | **Calendrier marketing annuel** et contenus proposés | Neocamino (plan d'actions guidé), Koban (scénarios) | Écran « Campagnes » : temps forts réglementaires et saisonniers, préparation par l'IA, validation, posts LinkedIn de la semaine à publier soi-même | ✅ | P3 |
| 10 | **Capture de contacts entrants** : guide à télécharger, simulateur « Combien de SST ? », formulaires | Koban, Neocamino, HubSpot | Formulaires sur le site de FORMA'ST → prospect créé avec consentement et besoin chiffré | Campagnes (février) | P3 |
| 11 | **Scoring comportemental** du site web (après consentement aux cookies) | Koban (suivi des visiteurs) | Signal « intérêt sur le site » ; uniquement pour les visiteurs identifiés qui ont consenti | Signal existant | P4 |
| 12 | **Tests A/B** d'objets et d'accroches | lemlist, La Growth Machine | Déjà prévu en §3.7 ; résultats par étape | — | P2 |
| 13 | **Prospects autour d'une session** | Spécifique FORMA'ST | « Autour de votre prochaine session » : prospects à moins de 25 km d'une session lue dans Planif ST, pour un passage le même jour | ✅ | P2 |
| 14 | **Enrichissement en cascade** | Outils d'enrichissement | Sources gratuites d'abord (SIRENE, site web, annuaire public), puis Pappers pour le CA et les dirigeants, puis service d'e-mails vérifiés ; arrêt dès qu'une source répond ; coût affiché | — | P2 |
| 15 | **Téléphonie intégrée** : appel en un clic, enchaînement, résumé par l'IA | Ringover, Aircall, Modjo | Session d'appels (déjà en maquette) ; P4 : appel depuis le navigateur via Microsoft Teams Phone ou un opérateur, résumé IA avec information des personnes appelées | Session d'appels ✅ | P4 |
| 16 | ~~Du devis à la facture~~ | Sellsy, Axonaut, Koban | **Hors périmètre** : outil de facturation existant relié à Penny Line | — | — |
| 17 | ~~Score prédictif des affaires~~ | HubSpot, Salesforce | **Hors périmètre** : le suivi des opportunités reste dans le CRM | — | — |
| 18 | **Thème clair / sombre**, interface utilisable sur mobile | Standard | Bascule de thème, file du jour et fiche lisibles sur téléphone | ✅ | P1 |

---

## 3 bis. Sellsy, Axonaut, HubSpot, Furious et Attio

L'agent est un **outil interne et propriétaire, centré sur l'aide à la prospection**. Les fonctions de gestion déjà couvertes par nos outils ne sont pas reprises :
- devis, facturation, trésorerie → outil de facturation existant, relié à Penny Line ;
- charge, planning et tournées des formateurs → Planif ST et l'optimiseur de tournées.

| Outil | Ce qu'il fait le mieux | Repris dans l'agent | Maquette | Phase |
|---|---|---|---|---|
| **Attio** | Attributs IA (une question → une colonne remplie par l'IA pour chaque ligne), listes de travail, force de la relation, automatisations sur un canevas visuel | **Colonnes IA** avec leur source ; **force de la relation** par contact ; automatisations en schéma Quand → Si → Alors | ✅ Prospects, fiche, automatisations | P1–P2 |
| **HubSpot** | Lien de prise de RDV relié à l'agenda Office ; guides d'appel qui remplissent la fiche ; séquences déclenchées par les automatisations | **3 créneaux libres** + lien de RDV insérés dans l'e-mail ; **guide de découverte** dans la session d'appels | ✅ Fiche, session d'appels | P2 |
| **Furious** | Taux de transformation et charge d'avant-vente | **Taux de transformation de la prospection** dans Statistiques (la charge des formateurs reste dans Planif ST) | ✅ Statistiques | P2 |
| **Sellsy** | Du devis à la facture, facture électronique | Non repris : outil de facturation existant | — | — |
| **Axonaut** | Devis, acomptes, trésorerie prévisionnelle | Non repris : outil de facturation existant | — | — |

## 4. Idées écartées

| Idée | Où on la trouve | Pourquoi l'écarter |
|---|---|---|
| Automatisation des invitations et messages LinkedIn | La Growth Machine, lemlist, Waalaxy | Contraire aux CGU de LinkedIn, risque de perte du compte, exposition RGPD |
| Achat de bases de contacts nominatives | Fournisseurs de données | Origine et consentement invérifiables ; sanctions CNIL récentes |
| Envois de masse et « réchauffement » artificiel de boîtes | Outils d'envoi en volume | Abîme la réputation du domaine ; inutile à notre volume (40 envois / jour / boîte) |
| Agent qui envoie seul aux nouveaux prospects dès le départ | Agents SDR | Le premier envoi reste validé tant que le taux de réponse n'est pas mesuré (mode par défaut : « premier envoi validé ») |
| Pixel de suivi d'ouverture activé par défaut | La plupart des outils | Encadré par la CNIL ; désactivé tant que ce n'est pas validé |

---

## 5. Sources

- Koban : [La Fabrique du Net](https://www.lafabriquedunet.fr/logiciel/koban), [Capterra](https://www.capterra.com/p/10007725/Koban/), [Rotek](https://rotek.fr/?p=45781), [GetApp](https://www.getapp.com/all-software/a/koban/)
- Neocamino : [Appvizer](https://www.appvizer.fr/marketing/automatisation-marketing/neocamino), [logiciels.pro](https://www.logiciels.pro/neocamino/), [Capterra](https://www.capterra.fr/software/181876/neocamino)
- Salesforce : [Prospecting Agent](https://www.salesforce.com/sales/prospecting/agent/), [Guide d'implémentation Agentforce for Sales Development](https://www.salesforce.com/en-us/wp-content/uploads/sites/4/documents/guides/Agentforce-for-Sales-Development-Implementation-Guide.pdf), [Piper, l'agent SDR de Salesforce](https://www.salesforce.com/salesforce-on-salesforce/agentic-presales-qualified-piper/)
- HubSpot : [AI Prospecting Agent](https://hubspot.com/products/sales/ai-prospecting-agent), [Base de connaissances](https://knowledge.hubspot.com/get-started-with-ai-powered-prospecting), [Spring 2025 Spotlight](https://www.hubspot.com/company-news/spring-2025-spotlight-breeze-agents)
- lemlist et La Growth Machine : [comparatif LGM](https://lagrowthmachine.com/fr/lemlist-vs-la-growth-machine/) (publié par l'éditeur), [Impli](https://www.impli.fr/comparaison/lemlist-vs-la-growth-machine), [Overloop](https://overloop.com/fr/blog/avis-la-growth-machine)
- Sellsy : [Sellsy, gestion commerciale](https://go.sellsy.com/fr/tous-les-modules/gestion-commerciale), [Blog du Modérateur](https://www.blogdumoderateur.com/tools/sellsy/), [Rotek](https://rotek.fr/?p=45768), [Breakcold](https://www.breakcold.com/fr/blog/sellsy-crm-avis)
- Axonaut : [Blog du Modérateur](https://www.blogdumoderateur.com/axonaut-solution-crm-factures-depenses/), [Codeur](https://www.codeur.com/comparatif/logiciel-facturation/axonaut), [Finance Héros](https://finance-heros.fr/avis-axonaut/)
- Furious : [Blog du Modérateur](https://www.blogdumoderateur.com/tools/furious/), [Appvizer](https://www.appvizer.fr/operations/erp/furious), [La Fabrique du Net](https://www.lafabriquedunet.fr/logiciel/furious)
- Attio : [AI attributes (Attio)](https://attio.com/blog/introducing-ai-attributes), [Attio AI (aide)](https://attio.com/help/reference/attio-ai), [CRM.org](https://crm.org/news/attio-review), [Sacra](https://sacra.com/research/attio)
- HubSpot Sales Hub : [Tarifs et fonctions](https://www.hubspot.com/pricing/sales)
- Pappers : [API Pappers](https://www.pappers.fr/api), [Fonctionnalités](https://www.pappers.fr/fonctionnalites)
- Pipedrive, Ringover, Aircall, Modjo, Dropcontact, Lusha : connaissance générale du marché, non revérifiée pour ce document. **Prix à confirmer.**
