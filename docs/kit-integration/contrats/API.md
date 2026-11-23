# Contrats d'API entre l'agent, le CRM et l'outil AO

Cahier des charges §3.14.2. Trois applications séparées, clé commune **SIREN**. Toutes les routes sont versionnées (`/api/v1/…`), en JSON UTF-8, en HTTPS.

## 0. Règles communes

| Sujet | Règle |
|---|---|
| Authentification | En-tête `Authorization: Bearer <jeton>`, **un jeton par application**, droits limités aux routes listées ici. Jetons dans `.env`, jamais dans le code |
| Réseau | Si les applications partagent un serveur : écoute sur le réseau local uniquement |
| Dates | ISO 8601, fuseau `Europe/Paris` à l'affichage, UTC en base |
| Erreurs | `{"erreur": {"code": "siren_invalide", "message": "…", "champ": "siren"}}` avec le statut HTTP approprié (400, 401, 403, 404, 409, 422, 429, 503) |
| Pagination | `?page=1&taille=50`, réponse `{"resultats": [...], "page": 1, "total": 312}` |
| Idempotence | Toute création accepte l'en-tête `Idempotency-Key` ; même clé = même réponse, sans doublon |
| Webhooks | Voir §4 : signés HMAC-SHA256, horodatés, rejouables |
| Mode dégradé | Si le CRM ne répond pas, l'agent met les écritures en file (`file_sortante`) et réessaie (1 min, 5 min, 30 min, 2 h, puis alerte) |

---

## 1. API à exposer par le CRM (consommée par l'agent)

| Méthode | Route | Usage | Corps / réponse |
|---|---|---|---|
| GET | `/api/v1/comptes?siren=…` | Savoir si un prospect est déjà client | `[CompteCRM]` |
| GET | `/api/v1/comptes?modifies_depuis=…` | Cache des clients (toutes les 15 min) | page de `CompteCRM` |
| POST | `/api/v1/comptes` | Créer le compte au RDV fixé | `CompteCRM` → `{id}` |
| PATCH | `/api/v1/comptes/{id}` | Mise à jour (statut, propriétaire) | champs partiels |
| GET / POST | `/api/v1/contacts?compte_id=…` | Contacts rattachés | `ContactCRM` |
| POST | `/api/v1/opportunites` | Opportunité créée au RDV fixé | `OpportuniteCRM` → `{id}` |
| GET | `/api/v1/opportunites/{id}` | Suivi : ouverte, gagnée, perdue (motif) | `OpportuniteCRM` |
| POST | `/api/v1/activites` | E-mails, appels, notes, avec lien vers la fiche de l'agent | `ActiviteCRM` |
| GET | `/api/v1/formations?siren=…&echeance_avant=…` | Formations réalisées → recyclages | `[FormationCRM]` |
| GET / POST | `/api/v1/oppositions?depuis=…` | Liste d'opposition commune | `{valeur, type, source, date}` |

Le CRM **ne transmet ni devis ni facture** à l'agent : la facturation reste dans l'outil existant relié à Penny Line.

### Objets

```json
// CompteCRM
{"id": "crm_123", "siren": "912345671", "nom": "Logistique du Vexin", "est_client": false,
 "proprietaire": "j.morel", "statut": "prospect", "modifie_le": "2026-11-20T08:12:00Z"}

// ContactCRM
{"id": "crm_c_45", "compte_id": "crm_123", "prenom": "Claire", "nom": "Vasseur",
 "fonction": "DRH", "email": "c.vasseur@exemple.example", "telephone": null, "oppose": false}

// OpportuniteCRM (création par l'agent)
{"compte_id": "crm_123", "contact_id": "crm_c_45", "titre": "Formation SST et évacuation — nouveau site",
 "source": "agent_prospection", "lien_agent": "https://prospection.interne/fiche/1",
 "besoin_estime": {"sst": 29, "sessions_sst": 3, "exercices_evacuation_an": 4, "potentiel_an1_eur": 21810},
 "brief": "Logistique du Vexin (Cergy, 95) : …", "rdv_le": "2026-11-26T10:00:00+01:00"}
// Réponse GET : + {"id": "opp_9", "etat": "ouverte|gagnee|perdue", "motif_perte": null, "concurrent": null}

// ActiviteCRM
{"compte_id": "crm_123", "contact_id": "crm_c_45", "type": "email|appel|note|rdv", "sens": "sortant",
 "date": "2026-11-20T09:12:00+01:00", "resume": "E-mail d'approche « nouveau site »", "lien_agent": "…"}

// FormationCRM
{"siren": "921234560", "etablissement_siret": null, "prestation": "MAC SST", "date_session": "2025-01-20",
 "nb_stagiaires": 12, "formateur": "Formateur A", "reference_planif_st": "PST-2025-0142"}
```

---

## 2. API à exposer par l'outil AO (lecture, consommée par l'agent)

| Méthode | Route | Contenu |
|---|---|---|
| GET | `/api/v1/ao/profil` | Identité, habilitations, points forts, zone |
| GET | `/api/v1/ao/catalogue` | Prestations : intitulé, catégorie, durée, groupe min/max, prix intra et inter (pour le potentiel estimé uniquement) |
| GET | `/api/v1/ao/references?citable=1` | Références citables, par secteur |
| GET | `/api/v1/ao/bibliotheque` | Blocs de contenu réutilisables |
| GET | `/api/v1/ao/acheteurs?depuis=…` | Acheteurs publics du périmètre, avec leurs avis (SIREN, nom, type, avis[]) |
| GET | `/api/v1/ao/attributions?cpv=80&depuis=…` | Attributions et DECP : titulaire, montant, date de fin estimée |
| POST | `/api/v1/ao/acheteurs-suivis` | L'agent signale un acheteur qualifié `{siren, raison, lien_agent}` |

Webhook émis par l'outil AO : `ao.resultat` (`{avis_id, acheteur_siren, statut: "gagne|perdu|sans_suite"}`).

---

## 3. API de l'agent (consommée par le CRM, pour l'intégration « tout ou partie »)

| Méthode | Route | Usage |
|---|---|---|
| GET | `/api/v1/prospects?siren=…` | Panneau dans la fiche compte du CRM : score, palier, explication, besoin, signaux, prochaine action |
| GET | `/api/v1/prospects/{id}` | Détail complet |
| POST | `/api/v1/prospects/{id}/message` | Rédaction : `{canal: "email|linkedin|appel|relance", contact_id, ton, consigne}` → `{objet, texte, note_qualite, controles[]}` |
| POST | `/api/v1/prospects/{id}/enrichir` | Lance l'enrichissement en cascade (asynchrone) |
| POST | `/api/v1/sequences/{id}/inscrire` | `{contact_ids: []}` |
| GET | `/api/v1/taches?pour=moi&jusqu_au=…` | File de tâches |
| GET | `/api/v1/journee` | Prochaines actions classées (même logique que « Ma journée ») |
| POST | `/api/v1/assistant` | `{question}` → `{reponse, propositions_d_action[]}` ; aucune écriture sans confirmation explicite |

---

## 4. Webhooks

**Émis par l'agent** : `prospect.cree`, `prospect.qualifie`, `prospect.score_change`, `reponse.recue`, `rdv.fixe`, `opposition.enregistree`.
**Reçus par l'agent** : `client.cree`, `opportunite.gagnee`, `opportunite.perdue`, `formation.realisee`, `opposition.enregistree` (CRM) ; `ao.resultat` (outil AO).

Enveloppe :

```json
{"id": "evt_01JD3K…", "type": "rdv.fixe", "cree_le": "2026-11-20T10:02:11Z", "source": "agent_prospection",
 "donnees": {"prospect_id": 1, "siren": "912345671", "contact_id": 3, "rdv_le": "2026-11-26T10:00:00+01:00"}}
```

En-têtes : `X-Signature: sha256=<hex>` et `X-Horodatage: <secondes epoch>`.
Signature : `HMAC_SHA256(secret_partage, horodatage + "." + corps_brut)`.
Le récepteur rejette si la signature ne correspond pas ou si l'horodatage a plus de 5 minutes ; il répond `200` dès réception et traite de façon **idempotente** sur `id` (un événement rejoué ne produit rien de plus).

Exemple de vérification (Python) :

```python
import hmac, hashlib, time
def verifier(secret: bytes, horodatage: str, corps: bytes, signature: str) -> bool:
    if abs(time.time() - int(horodatage)) > 300:
        return False
    attendu = "sha256=" + hmac.new(secret, horodatage.encode() + b"." + corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendu, signature)
```

## 5. Planif ST (optionnel, P2)

Lecture seule des sessions planifiées : `GET /api/v1/sessions?depuis=…&jusqu_au=…` → `[{reference, date_debut, lieu: {ville, latitude, longitude}, prestation, client_siren}]`. Sert uniquement à « Autour de votre prochaine session » (rayon 25 km). L'agent ne crée ni ne modifie de session.
