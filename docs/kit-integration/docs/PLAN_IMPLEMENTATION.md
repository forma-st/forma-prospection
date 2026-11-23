# Plan d'implémentation — Agent de prospection

Découpage en lots livrables, avec critères d'acceptation. Les phases suivent le cahier des charges (§8). La maquette (`../maquette/prospection.html`) fait référence pour les écrans et les comportements.

Convention : chaque lot = une branche, des tests automatiques, une démonstration sur données fictives (`../donnees/`).

---

## P1 — Base utile (mode autonome, 15 à 20 jours)

| Lot | Contenu | Critères d'acceptation |
|---|---|---|
| **1.1 Socle** | Module `prospection`, modèle de données (`../modele/schema.sql`), rôles (administrateur, commercial, assistant, lecture), journal d'audit, réglage `PROSPECTION_CRM = "autonome"` | Migrations appliquées ; un utilisateur « assistant » ne peut pas inscrire en séquence ; toute modification est journalisée avec avant / après |
| **1.2 Règles** | Chargement de `../regles/regles_metier.json` en base (segments, signaux, poids, paliers, échéances), modifiables par l'administrateur | Modifier un poids recalcule les scores ; valeurs par défaut restaurables |
| **1.3 Import** | CSV / XLSX, détection du séparateur et de l'encodage, correspondance automatique des colonnes (mémorisée par modèle de fichier), normalisation, dédoublonnage SIRET → SIREN → nom normalisé + CP → domaine, contrôle SIREN (Luhn), liste d'opposition, e-mails personnels signalés, rapport par ligne, annulation pendant 30 jours | Avec `../donnees/exemple_import_prospects.csv` : 4 nouveaux, 1 doublon, 2 à vérifier (SIRET invalide, e-mail personnel), 1 opposé — comme dans la maquette |
| **1.4 Rapprochement SIRENE** | Recherche par SIREN ou nom + commune (API Recherche d'entreprises), indice de confiance, < 80 % → « à vérifier » ; rafraîchissement nocturne | Fiche complétée avec NAF, tranche, établissements, IDCC ; entreprise fermée retirée des séquences |
| **1.5 Historique des formations** | Table, import (`../donnees/modele_import_historique_formations.csv`), saisie, calcul des échéances, relances | MAC SST du 20/01/2025 → échéance 20/01/2027, relance à J-90 ; bouton « Créer les relances dues » |
| **1.6 Besoin et score** | Calcul du besoin (SST, manutention, évacuation, potentiel) et des trois sous-scores ; explication en une phrase | Les valeurs des prospects fictifs correspondent à la maquette (ex. Logistique du Vexin : palier A, 89) |
| **1.7 Liste et fiche** | Liste filtrable, vues enregistrées, vue en colonnes (glisser-déposer), fiche avec barre d'actions fixe, navigation J / K, recherche Ctrl+K | Changement de statut par glisser-déposer journalisé ; « En séquence » refusé sans contact |
| **1.8 Rédaction** | Brief, e-mail, LinkedIn, script d'appel, relance (`../ia/PROMPTS.md`), ton et consigne, contrôle avant envoi (note sur 100), copier | Aucun texte sans pied de page RGPD ; note < 60 signalée ; champs `[À COMPLÉTER]` détectés |
| **1.9 Ma journée et tâches** | Prochaines actions classées (réponses, retards, échéances, prospects A), Fait / Demain, objectif du jour, file de tâches | L'ordre suit les priorités du cahier §3.18 ; « Demain » masque l'action jusqu'au lendemain |
| **1.10 Opposition** | Liste globale (e-mail, domaine), contrôle à l'import et à la rédaction, export et effacement d'une personne | Une adresse opposée ne peut recevoir aucun message, quel que soit le canal |

## P2 — Contacter (15 à 20 jours)

| Lot | Contenu | Critères d'acceptation |
|---|---|---|
| **2.1 Messagerie** | Boîtes Microsoft Graph (SMTP en repli), file idempotente, plafonds, plages horaires, jours ouvrés, **mode test** (redirection), relève toutes les 5 min, rattachement par en-têtes | Coupure simulée en plein envoi : aucun doublon ; mode test : aucun envoi externe |
| **2.2 Séquences** | Étapes e-mail / LinkedIn / appel / tâche, modes de validation, arrêts automatiques (réponse, RDV, opposition, rebond, absence) | Une réponse arrête la séquence du contact en moins de 5 min |
| **2.3 Tri des réponses** | Classement (`PROMPTS.md` §3), actions proposées, correction manuelle conservée comme jeu de test | ≥ 90 % de bons classements sur le jeu de 100 réponses |
| **2.4 Pilote automatique** | Niveaux par activité, budget, plafond, journal « cette nuit, l'agent a… », annulation 10 min | LinkedIn impossible à passer en automatique ; budget dépassé → retour en « propose » |
| **2.5 Enrichissement** | Cascade : SIRENE → site web → annuaire public → (option) Pappers → service d'e-mails vérifiés ; coût par contact | L'enrichissement s'arrête à la première source fiable ; coût visible sur la fiche |
| **2.6 RDV et appels** | 3 créneaux libres de l'agenda Microsoft 365 insérés dans l'e-mail, session d'appels avec guide de découverte | Les réponses du guide mettent à jour la fiche et l'écart de SST |
| **2.7 Colonnes IA et relation** | Colonnes préréglées et question libre, avec source ; force de la relation | Recalcul quand la fiche change ; « inconnu » si l'IA n'est pas sûre |
| **2.8 Statistiques** | Entonnoir, taux de transformation, rendement des sources, coût IA | Chiffres cohérents avec les tables `message`, `reponse`, `cout` |
| **2.9 Automatisations** | Moteur Quand → Si → Alors, recettes `../regles/automatisations.json`, simulation, journal | La simulation ne modifie rien ; chaque exécution est journalisée |

## P3 — Signaux et campagnes (15 à 20 jours)

BODACC, France Travail, Géorisques (ICPE), annuaire de l'administration, DECP et radar de renouvellement, veille web, score d'intention avec décroissance, assistant conversationnel (outils de `PROMPTS.md` §5), campagnes (`../regles/campagnes.json`), capture de contacts entrants (guide, simulateur SST).

## P4 — Intégration

Passerelle `crm_api` (`../contrats/API.md` §1), API AO (§2), API de l'agent (§3) et webhooks signés (§4), commande `migrer_vers_crm`, panneau dans la fiche compte du CRM, lecture des sessions de Planif ST (§5), téléphonie, recalibrage du score.

---

## Tests à écrire dès P1

- Dédoublonnage : mêmes SIRET, même SIREN, noms proches (« Logistique du Vexin SAS » = « Logistique du Vexin »).
- Score : cas limites des paliers (69 / 70), décroissance d'un signal à 0, 1 et 2 demi-vies.
- Échéances : 24 mois, 6 mois, fin de mois (31/08 + 6 mois).
- Opposition : e-mail exact, domaine `@exemple.example`, majuscules.
- Contrôle avant envoi : chaque règle isolément.
- RGPD : purge à 3 ans (liste avant suppression), export d'une personne.
