# Prompts et sorties structurées de l'IA

Cahier des charges §3.6, §3.8, §3.11, §3.19. Toutes les sorties sont validées par un schéma (Pydantic ou équivalent) ; une sortie invalide est rejetée et régénérée une fois, puis signalée.

## Règles communes (prompt système, mis en cache)

```
Tu es l'assistant de prospection interne de FORMA'ST, organisme de formation en santé et sécurité au travail
(SST, MAC SST, incendie et évacuation, UMFI, gestes et postures, QVT / RPS), Qualiopi et habilité INRS SST.

Règles absolues :
1. N'invente rien : aucun chiffre, nom, référence client ou fait qui ne figure pas dans les DONNÉES fournies.
   Si une information manque, écris [À COMPLÉTER : …].
2. Chaque fait sur le prospect cite sa source (champ "sources").
3. Vouvoiement, français courant, phrases courtes. Pas de superlatifs, pas de « je me permets ».
4. Mots interdits : gratuit, urgent, promo, exceptionnel, garanti, points d'exclamation multiples.
5. Une seule question d'appel à l'action par message.
6. Ne mentionne jamais un accident du travail, une visite du site web ou une ouverture d'e-mail du prospect.
7. Les références citables sont uniquement celles marquées "citable" dans les DONNÉES.

PROFIL FORMA'ST : {profil}            ← GET /api/v1/ao/profil
CATALOGUE : {catalogue}                ← GET /api/v1/ao/catalogue
RÉFÉRENCES CITABLES : {references}     ← GET /api/v1/ao/references?citable=1
```

## 1. Brief du compte

Entrée : fiche (identité SIRENE, segment, besoin estimé, signaux avec sources, contacts, historique).

```json
{"type":"object","required":["identite","risques","obligations","signal","angle","sources"],
 "properties":{
  "identite":{"type":"string","maxLength":300},
  "risques":{"type":"string","maxLength":300},
  "obligations":{"type":"string","maxLength":300},
  "signal":{"type":"string","maxLength":300},
  "angle":{"type":"string","maxLength":300},
  "sources":{"type":"array","items":{"type":"string"}}}}
```

## 2. Rédaction d'un message

Entrée : brief, contact visé (nom, fonction, rôle), canal, ton (`direct` | `institutionnel` | `chaleureux`), consigne libre, étape de séquence.

```json
{"type":"object","required":["objet","texte","sources","champs_a_completer"],
 "properties":{
  "objet":{"type":"string","maxLength":70},
  "texte":{"type":"string"},
  "sources":{"type":"array","items":{"type":"string"}},
  "champs_a_completer":{"type":"array","items":{"type":"string"}}}}
```

Contraintes par canal : e-mail 60 à 170 mots sans le pied de page ; LinkedIn ≤ 300 caractères, sans lien ; script d'appel = ouverture 20 s, 3 questions de découverte, 6 objections, conclusion avec 2 créneaux.
Le **pied de page RGPD** (source de la donnée, finalité, conservation, lien d'opposition) est ajouté par le code, jamais par l'IA.
Après génération, le code calcule la **note de contrôle** (regles_metier.json > controle_avant_envoi).

## 3. Classement d'une réponse (modèle économique)

```json
{"type":"object","required":["classe","confiance","resume"],
 "properties":{
  "classe":{"enum":["interesse","pas_maintenant","mauvais_interlocuteur","deja_equipe","absence","opposition","rebond","autre"]},
  "confiance":{"type":"integer","minimum":0,"maximum":100},
  "resume":{"type":"string","maxLength":200},
  "date_reprise":{"type":["string","null"],"format":"date"},
  "date_retour_absence":{"type":["string","null"],"format":"date"},
  "nouveau_contact":{"type":["object","null"],"properties":{"nom":{"type":"string"},"fonction":{"type":"string"},"email":{"type":"string"}}},
  "prestataire_cite":{"type":["string","null"]}}}
```

Règles : confiance < 80 → lecture humaine, aucune action. `opposition` → toujours appliquée, même à confiance faible (principe de précaution). Jeu de test : 100 réponses annotées, objectif ≥ 90 % de bons classements.

## 4. Colonnes IA

Entrée : question de la colonne + fiche du prospect. Sortie :

```json
{"type":"object","required":["valeur","source"],
 "properties":{"valeur":{"type":"string","maxLength":80},"source":{"type":"string"},"certitude":{"enum":["sure","probable","inconnue"]}}}
```

Questions préréglées : angle d'approche, décideur à viser, risque incendie, plusieurs sites à former, prestataire actuel, financement. « inconnue » s'affiche « Inconnu » ; une valeur de colonne IA n'est jamais réutilisée telle quelle dans un message sans vérification.

## 5. Assistant conversationnel (outils)

| Outil | Effet | Confirmation |
|---|---|---|
| `chercher_prospects(filtres)` | Lecture | non |
| `lire_fiche(id)` | Lecture | non |
| `expliquer_score(id)` | Lecture | non |
| `rechercher_sirene(nom, commune)` | Lecture externe | non |
| `preparer_rdv(id)` | Génère une fiche de préparation | non |
| `rediger(id, canal, consigne)` | Crée un brouillon | non |
| `creer_tache(id, type, echeance)` | Écriture | **oui** |
| `inscrire_sequence(ids, sequence_id)` | Écriture | **oui** |
| `changer_statut(id, statut)` | Écriture | **oui** |

Toute écriture est présentée à l'utilisateur (« Inscrire 4 prospects dans « Ouverture de site » ? ») et exécutée seulement après clic sur Confirmer.

## 6. Coûts

Chaque appel enregistre modèle, jetons, coût et objet dans la table `cout`. Modèle haut de gamme : brief, rédaction, assistant. Modèle économique : classement des réponses, colonnes IA, extraction d'articles. Profil, catalogue et références en cache de prompt.
