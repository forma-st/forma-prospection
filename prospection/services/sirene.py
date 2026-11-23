"""Rapprochement avec l'annuaire officiel des entreprises (API publique Recherche d'entreprises, gratuite).

https://recherche-entreprises.api.gouv.fr/docs/
"""

from __future__ import annotations

import difflib
import logging

from django.utils import timezone

from .http import get_json
from .texte import normaliser

from .. import regles
from ..models import Activite, Compte
from .scoring import recalculer

log = logging.getLogger("prospection.sirene")

PETITS_MOTS = {"de", "du", "des", "la", "le", "les", "d", "l", "sur", "sous", "en", "et", "lès", "les"}


def _titre(texte: str) -> str:
    """« MERY-SUR-OISE » -> « Mery-sur-Oise » (approximation lisible des libellés de l'annuaire)."""
    mots = []
    for m in (texte or "").lower().split(" "):
        parties = []
        for i, p in enumerate(m.split("-")):
            if "'" in p:
                a, b = p.split("'", 1)
                p = f"{a if a in PETITS_MOTS else a.capitalize()}'{b.capitalize()}"
            elif p not in PETITS_MOTS or (i == 0 and not mots):
                p = p.capitalize()
            parties.append(p)
        mots.append("-".join(parties))
    return " ".join(mots)
URL = "https://recherche-entreprises.api.gouv.fr/search"


def _confiance(c: Compte, r: dict) -> int:
    a = normaliser(c.nom)
    b = normaliser(r.get("nom_complet") or r.get("nom_raison_sociale") or "")
    score = difflib.SequenceMatcher(None, a, b).ratio() * 80
    siege = r.get("siege") or {}
    if c.code_postal and siege.get("code_postal") == c.code_postal:
        score += 20
    elif c.departement and (siege.get("code_postal") or "")[:2] == c.departement:
        score += 10
    if c.siren and r.get("siren") == c.siren:
        score = 100
    return min(100, round(score))


def chercher(c: Compte) -> tuple[dict | None, int]:
    if c.siren:
        params = {"q": c.siren, "per_page": 1}
    else:
        params = {"q": c.nom, "per_page": 5}
        if c.code_postal:
            params["code_postal"] = c.code_postal
        elif c.departement:
            params["departement"] = c.departement
    data = get_json(URL, params=params)
    meilleurs = sorted(((r, _confiance(c, r)) for r in data.get("results", [])), key=lambda x: -x[1])
    return meilleurs[0] if meilleurs else (None, 0)


def appliquer(c: Compte, r: dict, confiance: int, utilisateur=None) -> Compte:
    siege = r.get("siege") or {}
    c.siren = r.get("siren") or c.siren
    c.siret = siege.get("siret") or c.siret
    naf = r.get("activite_principale") or siege.get("activite_principale") or ""
    if naf:
        c.naf = naf
        if c.segment == "autre":
            c.segment = regles.segment_depuis_naf(naf)
    tranche = r.get("tranche_effectif_salarie") or siege.get("tranche_effectif_salarie")
    if tranche in regles.TRANCHES and regles.TRANCHES[tranche]:
        c.effectif = regles.TRANCHES[tranche]
    c.nb_etablissements = r.get("nombre_etablissements_ouverts") or c.nb_etablissements
    c.code_postal = siege.get("code_postal") or c.code_postal
    c.ville = _titre(siege.get("libelle_commune") or "") or c.ville
    c.departement = (siege.get("departement") or c.code_postal[:2] or c.departement)
    for k in ("latitude", "longitude"):
        try:
            setattr(c, k, float(siege.get(k)))
        except (TypeError, ValueError):
            pass
    idcc = (r.get("complements") or {}).get("liste_idcc") or siege.get("liste_idcc") or []
    if idcc:
        c.idcc = ", ".join(idcc[:3])
    c.sirene_le, c.sirene_confiance = timezone.now(), confiance
    if r.get("etat_administratif") == "C":
        c.statut = "Écarté"
        Activite.objects.create(compte=c, type="systeme", texte="Entreprise fermée selon l'annuaire : écartée.", utilisateur=utilisateur)
    c.save()
    Activite.objects.create(compte=c, type="systeme", texte=f"Rapproché avec l'annuaire (SIREN {c.siren}, confiance {confiance} %).", utilisateur=utilisateur)
    return recalculer(c)


def rapprocher(c: Compte, utilisateur=None, seuil: int = 80) -> tuple[bool, str]:
    try:
        r, conf = chercher(c)
    except Exception as e:  # réseau, quota
        log.warning("Annuaire indisponible pour %s : %s", c, e)
        return False, "L'annuaire des entreprises ne répond pas. Réessayez plus tard."
    if not r:
        return False, "Aucune entreprise trouvée dans l'annuaire avec ce nom."
    if conf < seuil:
        nom = r.get("nom_complet", "?")
        return False, f"Correspondance incertaine ({conf} %) : « {nom} », SIREN {r.get('siren')}. Saisissez le SIREN pour confirmer."
    appliquer(c, r, conf, utilisateur)
    return True, f"Fiche complétée depuis l'annuaire (SIREN {c.siren})."
