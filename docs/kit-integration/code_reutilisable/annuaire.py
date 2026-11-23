"""Mise à jour de l'identité légale depuis l'annuaire officiel des entreprises.

API publique et gratuite (DINUM, données INSEE / RNE) :
https://recherche-entreprises.api.gouv.fr/docs/
Ne remplace que les champs fournis par l'annuaire ; les champs saisis à la main
(CA, e-mail, téléphone, capital…) ne sont jamais écrasés par une valeur vide.
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone

from ..models import Entreprise
from .http import get_json
from .texte import normaliser

URL = "https://recherche-entreprises.api.gouv.fr/search"

FORMES = {
    "5499": "SARL", "5498": "EURL", "5710": "SAS", "5720": "SASU", "5599": "SA",
    "1000": "Entrepreneur individuel", "9220": "Association déclarée",
}
TRANCHES = {
    "00": "0 salarié", "01": "1 ou 2 salariés", "02": "3 à 5 salariés", "03": "6 à 9 salariés",
    "11": "10 à 19 salariés", "12": "20 à 49 salariés", "21": "50 à 99 salariés",
    "22": "100 à 199 salariés", "31": "200 à 249 salariés", "32": "250 à 499 salariés",
}


def tva_intracommunautaire(siren: str) -> str:
    if not (siren and siren.isdigit() and len(siren) == 9):
        return ""
    cle = (12 + 3 * (int(siren) % 97)) % 97
    return f"FR{cle:02d}{siren}"


def _titre(texte: str) -> str:
    """« 31 RUE DE L'ISLE-ADAM » -> « 31 rue de l'Isle-Adam » (approximation lisible)."""
    petits = {"de", "du", "des", "la", "le", "les", "d", "l", "rue", "avenue", "boulevard", "chemin", "allee",
              "impasse", "place", "route", "quai", "et", "sur", "sous", "en"}
    mots = []
    for m in texte.lower().split(" "):
        parties = []
        for p in m.split("-"):
            if "'" in p:
                a, b = p.split("'", 1)
                p = f"{a if a in petits else a.capitalize()}'{b.capitalize()}"
            elif p not in petits:
                p = p.capitalize()
            parties.append(p)
        mots.append("-".join(parties))
    return " ".join(mots)


def chercher(siren: str) -> dict:
    data = get_json(URL, params={"q": siren, "per_page": 1})
    for r in data.get("results", []):
        if r.get("siren") == siren:
            return r
    raise ValueError(f"SIREN {siren} introuvable dans l'annuaire des entreprises.")


def mettre_a_jour(e: Entreprise) -> list[str]:
    """Met à jour la fiche ; renvoie la liste des champs modifiés."""
    siren = (e.siret or "")[:9]
    if len(siren) != 9:
        raise ValueError("Renseignez d'abord le SIRET de l'entreprise.")
    r = chercher(siren)
    siege = r.get("siege") or {}
    comp = r.get("complements") or {}
    dirigeant = next((d for d in r.get("dirigeants", []) if d.get("type_dirigeant") == "personne physique"), None)

    nouvelles = {
        "raison_sociale": r.get("nom_raison_sociale") or r.get("nom_complet"),
        "forme_juridique": FORMES.get(str(r.get("nature_juridique") or ""), ""),
        "siret": siege.get("siret"),
        "tva_intracommunautaire": tva_intracommunautaire(siren),
        "code_naf": r.get("activite_principale"),
        "date_creation": date.fromisoformat(r["date_creation"]) if r.get("date_creation") else None,
        "tranche_effectif": TRANCHES.get(r.get("tranche_effectif_salarie") or "", ""),
        "qualiopi": True if comp.get("est_qualiopi") else None,
        "numero_declaration_activite": (comp.get("liste_id_organisme_formation") or [None])[0],
    }
    if siege.get("adresse") and siege.get("code_postal"):
        adresse = siege["adresse"].split(siege["code_postal"])[0].strip()
        nouvelles.update(
            adresse=_titre(adresse), code_postal=siege["code_postal"], ville=_titre(siege.get("libelle_commune") or "")
        )
    if dirigeant:
        prenoms = " ".join(p.capitalize() for p in (dirigeant.get("prenoms") or "").split())
        nouvelles["representant_nom"] = f"{prenoms} {(dirigeant.get('nom') or '').capitalize()}".strip()
        nouvelles["representant_qualite"] = dirigeant.get("qualite") or e.representant_qualite

    modifies = []
    for champ, valeur in nouvelles.items():
        if valeur in (None, ""):
            continue
        actuel = getattr(e, champ)
        if isinstance(valeur, str) and isinstance(actuel, str) and normaliser(actuel) == normaliser(valeur):
            continue  # même valeur, on garde la graphie saisie (accents, majuscules)
        if actuel != valeur:
            setattr(e, champ, valeur)
            modifies.append(champ)
    e.maj_annuaire_le = timezone.now()
    e.save()
    return modifies


# Champs utilisés dans les documents générés : (champ, libellé, obligatoire)
CHAMPS_DOCUMENTS = [
    ("email", "Adresse électronique", True),
    ("telephone", "Téléphone", True),
    ("ca_n1", "Chiffre d'affaires N-1", True),
    ("ca_n2", "Chiffre d'affaires N-2", True),
    ("ca_n3", "Chiffre d'affaires N-3", True),
    ("effectif", "Effectif exact", False),
    ("capital", "Capital social", False),
    ("qualiopi_expiration", "Date d'expiration Qualiopi", True),
    ("habilitation_inrs_sst_expiration", "Date d'expiration habilitation INRS SST", True),
    ("etablissements", "Autres établissements", False),
]


def completude(e: Entreprise | None) -> list[dict]:
    if not e:
        return []
    return [
        {"champ": c, "libelle": l, "obligatoire": o, "rempli": getattr(e, c) not in (None, "")}
        for c, l, o in CHAMPS_DOCUMENTS
    ]
