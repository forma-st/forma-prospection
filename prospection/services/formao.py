"""Connexion facultative à FORM'AO (outil de suivi, veille et gestion des appels d'offres).

Les deux outils restent indépendants : la Prospection fonctionne sans FORM'AO. Si FORMAO_URL et FORMAO_JETON
sont renseignés dans le .env, elle peut lire chez FORM'AO, en lecture seule :
- le profil de l'entreprise et le catalogue (pour ne pas les saisir deux fois) ;
- les acheteurs publics qui ont publié des avis retenus par la veille (prospects à suivre commercialement).

Contrat d'API attendu côté FORM'AO : docs/API_FORMAO.md.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx
from django.conf import settings
from django.utils import timezone

log = logging.getLogger("prospection.formao")


class FormaoIndisponible(Exception):
    pass


def configuree() -> bool:
    return bool(settings.FORMAO_URL and settings.FORMAO_JETON)


def _get(chemin: str, **params):
    if not configuree():
        raise FormaoIndisponible("La connexion à FORM'AO n'est pas configurée (FORMAO_URL et FORMAO_JETON dans le .env).")
    try:
        r = httpx.get(f"{settings.FORMAO_URL}/api/v1/{chemin}", params=params, timeout=20,
                      headers={"Authorization": f"Bearer {settings.FORMAO_JETON}", "User-Agent": "prospection-formast/1.0"})
    except httpx.HTTPError as e:
        raise FormaoIndisponible(f"FORM'AO ne répond pas ({e.__class__.__name__}).") from e
    if r.status_code in (401, 403):
        raise FormaoIndisponible("FORM'AO refuse le jeton : vérifiez FORMAO_JETON.")
    if r.status_code == 404:
        raise FormaoIndisponible("FORM'AO n'expose pas encore cette API (voir docs/API_FORMAO.md).")
    if r.status_code != 200:
        raise FormaoIndisponible(f"FORM'AO a répondu {r.status_code}.")
    return r.json()


def synchroniser_profil_et_catalogue() -> tuple[int, int]:
    """Reprend le profil et le catalogue de FORM'AO. Renvoie (prestations créées, mises à jour)."""
    from ..models import Prestation, ProfilEntreprise

    p = _get("profil")
    prof = ProfilEntreprise.get()
    for champ in ("nom", "presentation", "habilitations", "points_forts", "references_citables"):
        if p.get(champ):
            v = p[champ]
            setattr(prof, champ, "\n".join(v) if isinstance(v, list) else v)
    prof.synchronise_le = timezone.now()
    prof.save()

    crees = maj = 0
    for x in _get("catalogue").get("resultats", []):
        ref = str(x.get("id", ""))
        obj = Prestation.objects.filter(reference_formao=ref).first() if ref else None
        donnees = {"intitule": x.get("intitule", "?"), "duree": x.get("duree", "") or "", "prix_intra_ht": x.get("prix_intra_ht"),
                   "usage_potentiel": _usage(x.get("intitule", ""), x.get("categorie", "")), "exemple": False, "actif": x.get("actif", True)}
        if obj:
            for k, v in donnees.items():
                setattr(obj, k, v)
            obj.save()
            maj += 1
        else:
            Prestation.objects.create(reference_formao=ref, **donnees)
            crees += 1
    if crees or maj:
        Prestation.objects.filter(exemple=True, reference_formao="").update(actif=False)
    return crees, maj


def _usage(intitule: str, categorie: str) -> str:
    from .texte import normaliser
    n = normaliser(intitule)
    if "mac" in n or "recycl" in n:
        return "mac"
    if "sst" in n or "secour" in n:
        return "sst"
    if "geste" in n or "posture" in n:
        return "gp"
    if (categorie or "").upper() == "INCENDIE" or "incendie" in n or "evacu" in n:
        return "incendie"
    return "autre"


def acheteurs(depuis: date | None = None) -> list[dict]:
    """[{nom, siren, departement, avis: [{objet, url, date_publication, statut}]}]"""
    params = {"depuis": depuis.isoformat()} if depuis else {}
    return _get("acheteurs", **params).get("resultats", [])
