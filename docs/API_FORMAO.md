# Lien facultatif entre la Prospection et FORM'AO

Les deux outils sont **indépendants** : chacun a son code, sa base, ses comptes et son installation. La Prospection fonctionne entièrement sans FORM'AO.

Si on les relie, la Prospection **lit** dans FORM'AO, sans jamais écrire :

| Besoin de la Prospection | Route FORM'AO | Usage |
|---|---|---|
| Profil de l'entreprise | `GET /api/v1/profil` | Rédaction (présentation, habilitations, points forts, références citables) |
| Catalogue | `GET /api/v1/catalogue` | Potentiel estimé (prix intra des sessions) |
| Acheteurs publics | `GET /api/v1/acheteurs?depuis=AAAA-MM-JJ` | Un prospect par acheteur, un signal « acheteur public actif » par avis retenu par la veille : suivi commercial des acheteurs |

## Réglages côté Prospection (`.env`)

```
FORMAO_URL=http://localhost:8000
FORMAO_JETON=un-jeton-long-et-aleatoire
```

Boutons dans *Import de fichiers → Connexion à FORM'AO* : « Importer les acheteurs publics » et « Reprendre le profil et le catalogue ».

## Contrat à implémenter côté FORM'AO

Authentification : en-tête `Authorization: Bearer <FORMAO_JETON>`, même jeton déclaré dans le `.env` de FORM'AO (par exemple `PROSPECTION_JETON`). Réponse `401` si absent ou faux. Lecture seule, JSON UTF-8.

```json
// GET /api/v1/profil
{"nom": "FORMA'ST", "presentation": "…", "habilitations": "Qualiopi ; habilitation INRS SST",
 "points_forts": ["Unité mobile incendie", "Formateurs sapeurs-pompiers"], "references_citables": ["Enseigne nationale de 1 200 magasins"]}

// GET /api/v1/catalogue
{"resultats": [{"id": 7, "intitule": "Sauveteur secouriste du travail", "categorie": "SECOURISME",
                "duree": "2j", "prix_intra_ht": 1450.0, "actif": true}]}

// GET /api/v1/acheteurs?depuis=2026-06-01
{"resultats": [{"nom": "Ville de …", "siren": "219500000", "departement": "95",
                "avis": [{"objet": "Formation SST des agents", "url": "https://…", "date_publication": "2026-11-02", "statut": "DETECTE"}]}]}
```

### Exemple d'implémentation (Django, à adapter au code actuel de FORM'AO)

```python
# veille/api.py
import hmac, os
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .models import AvisMarche, Entreprise, Prestation, Reference

def _autorise(request):
    attendu = os.environ.get("PROSPECTION_JETON", "")
    recu = request.headers.get("Authorization", "").removeprefix("Bearer ")
    return bool(attendu) and hmac.compare_digest(attendu, recu)

def _refus():
    return JsonResponse({"erreur": "jeton invalide"}, status=401)

@require_GET
def profil(request):
    if not _autorise(request): return _refus()
    e = Entreprise.get()
    return JsonResponse({
        "nom": str(e), "presentation": e.presentation,
        "habilitations": " ; ".join(x for x in ["Qualiopi" if e.qualiopi else "", "Habilitation INRS SST" if e.habilitation_inrs_sst else "", e.autres_certifications] if x),
        "points_forts": [l for l in e.points_forts.splitlines() if l.strip()],
        "references_citables": [f"{r.client} : {r.objet}" for r in Reference.objects.filter(citable=True)],
    })

@require_GET
def catalogue(request):
    if not _autorise(request): return _refus()
    return JsonResponse({"resultats": [{"id": p.pk, "intitule": p.intitule, "categorie": p.categorie, "duree": p.duree,
        "prix_intra_ht": float(p.prix_intra_ht) if p.prix_intra_ht is not None else None, "actif": p.actif} for p in Prestation.objects.all()]})

@require_GET
def acheteurs(request):
    if not _autorise(request): return _refus()
    qs = AvisMarche.objects.filter(prefiltre_ok=True).exclude(acheteur="")
    if request.GET.get("depuis"): qs = qs.filter(date_publication__gte=request.GET["depuis"])
    par_nom = {}
    for a in qs.order_by("-date_publication")[:2000]:
        x = par_nom.setdefault(a.acheteur, {"nom": a.acheteur, "siren": "", "departement": (a.departements or "").split(",")[0], "avis": []})
        x["avis"].append({"objet": a.objet[:200], "url": a.url, "date_publication": a.date_publication.isoformat() if a.date_publication else None, "statut": a.statut})
    return JsonResponse({"resultats": list(par_nom.values())})

# config/urls.py
#   path("api/v1/profil", api.profil), path("api/v1/catalogue", api.catalogue), path("api/v1/acheteurs", api.acheteurs),
```

### Message à donner à la session Claude Code qui développe FORM'AO

```
Ajoute à FORM'AO une petite API en lecture seule pour Forma Prospect (application séparée) :
GET /api/v1/profil, /api/v1/catalogue, /api/v1/acheteurs?depuis=…, protégée par l'en-tête
Authorization: Bearer <PROSPECTION_JETON> (variable du .env, comparaison à temps constant, 401 sinon).
Le contrat exact et un exemple d'implémentation sont dans docs/API_FORMAO.md de Forma Prospect
(colle-le ici). Ajoute des tests (jeton absent, faux, bon) et n'expose aucun prix ni donnée si le jeton
n'est pas configuré.
```

## Évolutions possibles (suivi commercial)

- Prospection → FORM'AO : signaler qu'un acheteur public est suivi commercialement (`POST /api/v1/acheteurs-suivis`), pour l'afficher dans la fiche de ses avis.
- FORM'AO → Prospection : lorsqu'un AO est gagné, créer ou mettre à jour le client dans la Prospection (relances de recyclage).

Ces échanges seront à ajouter quand le besoin sera confirmé ; ils suivront les mêmes règles (jeton par application, lecture seule par défaut).
