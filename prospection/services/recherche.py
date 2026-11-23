"""Recherche automatique de prospects (cahier des charges §3.1, phase 3).

Chaque nuit, chaque recherche active interroge une source publique gratuite, filtre selon la cible, écarte les doublons,
les clients, les opposés et les entreprises fermées, calcule le score et ne garde que les prospects au-dessus du palier
minimum. Les nouveaux prospects arrivent « À qualifier » : rien n'est contacté sans validation.

Sources :
- sirene     : API Recherche d'entreprises (DINUM) — entreprises correspondant à la cible (NAF, départements, effectif) ;
- bodacc     : annonces BODACC de création d'établissement — signal « nouvel établissement » ;
- georisques : installations classées (ICPE) — sites industriels à fort besoin incendie / évacuation.

Les réponses de BODACC et de Géorisques sont lues de façon tolérante (plusieurs noms de champs possibles) :
une source qui change de format est signalée dans le journal, sans bloquer les autres.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta

from django.utils import timezone

from .. import regles
from ..models import Activite, Compte, ExecutionRecherche, RechercheAuto, Signal
from .http import get_json
from .scoring import recalculer
from .sirene import URL as URL_SIRENE, appliquer as appliquer_sirene
from .texte import normaliser

log = logging.getLogger("prospection.recherche")

URL_BODACC = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"
URL_GEORISQUES = "https://georisques.gouv.fr/api/v1/installations_classees"

# Tranches INSEE dont le bas est au moins l'effectif demandé
TRANCHES_MIN = [("11", 10), ("12", 20), ("21", 50), ("22", 100), ("31", 200), ("32", 250), ("41", 500), ("42", 1000), ("51", 2000), ("52", 5000), ("53", 10000)]
SECTIONS = [(10, 33, "C"), (35, 35, "D"), (36, 39, "E"), (41, 43, "F"), (45, 47, "G"), (49, 53, "H"), (55, 56, "I"), (58, 63, "J"),
            (64, 66, "K"), (68, 68, "L"), (69, 75, "M"), (77, 82, "N"), (84, 84, "O"), (85, 85, "P"), (86, 88, "Q"), (90, 93, "R"), (94, 96, "S")]
PAUSE = 0.25  # l'annuaire accepte environ 7 requêtes par seconde
PAGES_PAR_NUIT = 8
# Un prospect tout juste trouvé n'a ni contact ni signal : on le juge sur son adéquation à la cible.
ADEQUATION_MIN = {"A": 80, "B": 65, "C": 0}


def tranches_depuis(effectif_min: int, effectif_max: int = 0) -> list[str]:
    t = [code for code, bas in TRANCHES_MIN if bas >= effectif_min and (not effectif_max or bas < effectif_max)]
    return t or [code for code, _ in TRANCHES_MIN[-3:]]


def section_de(division: str) -> str | None:
    try:
        d = int(division[:2])
    except ValueError:
        return None
    return next((s for a, b, s in SECTIONS if a <= d <= b), None)


def correspond_naf(naf: str, filtres: list[str]) -> bool:
    if not filtres:
        return True
    n = (naf or "").upper()
    return any(n == f or (len(f) <= 3 and n.replace(".", "").startswith(f.replace(".", ""))) for f in filtres)


def _existe(siren: str, nom: str) -> Compte | None:
    if siren:
        c = Compte.objects.filter(siren=siren).first()
        if c:
            return c
    n = re.sub(r"[^a-z0-9]+", " ", normaliser(nom or "")).strip()
    return Compte.objects.filter(nom_normalise=n).first() if n else None


def _garder(c: Compte, r: RechercheAuto) -> bool:
    return c.score_adequation >= ADEQUATION_MIN[r.palier_min]


def _creer_depuis_sirene(res: dict, r: RechercheAuto, ex: ExecutionRecherche, signal: tuple | None = None) -> Compte | None:
    """Crée le prospect à partir d'un résultat de l'annuaire, le note, et le supprime s'il est sous le palier minimum."""
    siege = res.get("siege") or {}
    c = Compte(nom=res.get("nom_complet") or res.get("nom_raison_sociale") or "?", siren=res.get("siren", ""),
               code_postal=siege.get("code_postal") or "", segment=r.segment or regles.segment_depuis_naf(res.get("activite_principale", "")),
               statut="À qualifier", source=f"Recherche auto : {r.nom}")
    c.save()
    appliquer_sirene(c, res, 100)
    if r.segment:
        c.segment = r.segment
        c.save(update_fields=["segment"])
    if signal:
        type_, texte, src, url, d = signal
        Signal.objects.create(compte=c, type=type_, texte=texte[:300], source=src, url=url or "", date_signal=d or timezone.localdate())
    recalculer(c)
    if not _garder(c, r) or c.statut == "Écarté":
        c.delete()
        ex.ignores += 1
        return None
    Activite.objects.create(compte=c, type="systeme", texte=f"Trouvé par la recherche automatique « {r.nom} » ({c.explication})")
    ex.crees += 1
    ex.comptes.add(c)
    return c


def _sirene_par_siren(siren: str) -> dict | None:
    data = get_json(URL_SIRENE, params={"q": siren, "per_page": 1})
    time.sleep(PAUSE)
    return next((x for x in data.get("results", []) if x.get("siren") == siren), None)


def _filtre_entreprise(res: dict, r: RechercheAuto) -> bool:
    if res.get("etat_administratif") == "C":
        return False
    if not correspond_naf(res.get("activite_principale") or "", r.liste_naf()):
        return False
    t = res.get("tranche_effectif_salarie") or (res.get("siege") or {}).get("tranche_effectif_salarie")
    eff = regles.TRANCHES.get(t or "", 0)
    if eff < r.effectif_min or (r.effectif_max and eff > r.effectif_max):
        return False
    if (res.get("nombre_etablissements_ouverts") or 1) < r.etablissements_min:
        return False
    deps = r.liste_departements()
    if deps:
        siege = res.get("siege") or {}
        dep = siege.get("departement") or (siege.get("code_postal") or "")[:2]
        etabs = [e.get("departement") or (e.get("code_postal") or "")[:2] for e in (res.get("matching_etablissements") or [])]
        if dep not in deps and not any(d in deps for d in etabs):
            return False
    return True


# ------------------------------------------------------------------ sources


def chercher_sirene(r: RechercheAuto, ex: ExecutionRecherche) -> None:
    naf = r.liste_naf()
    exacts = [n for n in naf if re.fullmatch(r"\d{2}\.\d{2}[A-Z]", n)]
    divisions = [n for n in naf if n not in exacts]
    params = {"per_page": 25, "tranche_effectif_salarie": ",".join(tranches_depuis(r.effectif_min, r.effectif_max)), "etat_administratif": "A"}
    if exacts and not divisions:
        params["activite_principale"] = ",".join(exacts)
    elif divisions:
        sections = sorted({s for s in (section_de(d) for d in divisions) if s})
        if sections:
            params["section_activite_principale"] = ",".join(sections)
    if r.liste_departements():
        params["departement"] = ",".join(r.liste_departements())
    page = r.page_suivante
    for _ in range(PAGES_PAR_NUIT):
        data = get_json(URL_SIRENE, params={**params, "page": page})
        time.sleep(PAUSE)
        resultats = data.get("results", [])
        for res in resultats:
            ex.examines += 1
            if not _filtre_entreprise(res, r) or _existe(res.get("siren", ""), res.get("nom_complet", "")):
                ex.ignores += 1
                continue
            _creer_depuis_sirene(res, r, ex)
            if ex.crees >= r.max_par_nuit:
                break
        total_pages = data.get("total_pages") or 1
        fin = page >= total_pages
        page = 1 if fin else page + 1
        if ex.crees >= r.max_par_nuit or not resultats or fin:
            break
    r.page_suivante = page


def chercher_bodacc(r: RechercheAuto, ex: ExecutionRecherche, depuis: date | None = None) -> None:
    depuis = depuis or (timezone.localdate() - timedelta(days=7))
    where = [f'familleavis="creation"', f'dateparution>="{depuis.isoformat()}"']
    if r.liste_departements():
        where.append("(" + " or ".join(f'numerodepartement="{d}"' for d in r.liste_departements()) + ")")
    offset, vus = 0, set()
    while offset < 1000 and ex.crees < r.max_par_nuit:
        data = get_json(URL_BODACC, params={"where": " and ".join(where), "order_by": "dateparution desc", "limit": 100, "offset": offset})
        lignes = data.get("results", [])
        if not lignes:
            break
        for a in lignes:
            sirens = a.get("registre") or []
            sirens = sirens if isinstance(sirens, list) else [sirens]
            siren = next((re.sub(r"\D", "", s)[:9] for s in sirens if len(re.sub(r"\D", "", s)) >= 9), "")
            if not siren or siren in vus:
                continue
            vus.add(siren)
            ex.examines += 1
            texte = f"Création d'établissement publiée au BODACC ({a.get('ville') or a.get('numerodepartement') or ''})".replace(" ()", "")
            d = a.get("dateparution")
            signal = ("site", texte, "BODACC", a.get("url_complete") or "", date.fromisoformat(d[:10]) if d else None)
            existant = Compte.objects.filter(siren=siren).first()
            if existant:
                if not existant.signaux.filter(type="site", source="BODACC", date_signal=signal[4] or timezone.localdate()).exists():
                    Signal.objects.create(compte=existant, type="site", texte=texte, source="BODACC", url=signal[3], date_signal=signal[4] or timezone.localdate())
                    recalculer(existant)
                    ex.signaux += 1
                continue
            res = _sirene_par_siren(siren)
            if not res or not _filtre_entreprise(res, r):
                ex.ignores += 1
                continue
            _creer_depuis_sirene(res, r, ex, signal)
            if ex.crees >= r.max_par_nuit:
                break
        offset += 100


def _champ(x: dict, *noms):
    for n in noms:
        v = x.get(n)
        if v:
            return v
    return ""


def chercher_georisques(r: RechercheAuto, ex: ExecutionRecherche) -> None:
    deps = r.liste_departements() or [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]
    # parcourt les départements nuit après nuit (page_suivante = rang du département)
    debut = (r.page_suivante - 1) % len(deps)
    for k in range(len(deps)):
        dep = deps[(debut + k) % len(deps)]
        data = get_json(URL_GEORISQUES, params={"departement": dep, "page": 1, "page_size": 100})
        time.sleep(PAUSE)
        for x in data.get("data", data.get("results", [])) if isinstance(data, dict) else []:
            ex.examines += 1
            siret = re.sub(r"\D", "", str(_champ(x, "siret", "numeroSiret", "siretEtablissement")))
            siren = siret[:9]
            regime = str(_champ(x, "regime", "regimeVigueur", "libelleRegime"))
            seveso = str(_champ(x, "statutSeveso", "seveso"))
            existant = Compte.objects.filter(siren=siren).first() if siren else None
            if existant:
                if not existant.icpe:
                    existant.icpe = True
                    existant.save(update_fields=["icpe"])
                    recalculer(existant)
                    ex.signaux += 1
                continue
            if not siren or not correspond_naf(str(_champ(x, "codeNaf", "naf", "activitePrincipale")).replace(" ", ""), r.liste_naf()):
                ex.ignores += 1
                continue
            res = _sirene_par_siren(siren)
            if not res or not _filtre_entreprise(res, r):
                ex.ignores += 1
                continue
            c = _creer_depuis_sirene(res, r, ex)
            if c:
                c.icpe = True
                c.notes = f"Site ICPE ({regime or 'régime ?'}{', Seveso ' + seveso if seveso and seveso.lower() not in ('non seveso', 'ns') else ''}) : {_champ(x, 'raisonSociale', 'nom')} – {_champ(x, 'commune', 'adresse3', 'libelleCommune')}"
                c.save(update_fields=["icpe", "notes"])
                recalculer(c)
            if ex.crees >= r.max_par_nuit:
                r.page_suivante = (debut + k) % len(deps) + 1
                return
    r.page_suivante = 1


SOURCES = {"sirene": chercher_sirene, "bodacc": chercher_bodacc, "georisques": chercher_georisques}


def executer(r: RechercheAuto) -> ExecutionRecherche:
    ex = ExecutionRecherche.objects.create(recherche=r)
    try:
        SOURCES[r.source](r, ex)
    except Exception as e:  # une source en panne ne bloque pas les autres
        log.warning("Recherche « %s » : %s", r, e)
        ex.erreur = f"{e.__class__.__name__} : {e}"[:1000]
    r.derniere_execution = timezone.now()
    r.save(update_fields=["page_suivante", "derniere_execution"])
    ex.save()
    return ex


def executer_tout(forcer: bool = False) -> list[ExecutionRecherche]:
    return [executer(r) for r in RechercheAuto.objects.filter(actif=True) if forcer or r.active_ce_mois()]


def bilan_nuit(heures: int = 24) -> dict:
    qs = ExecutionRecherche.objects.filter(debut__gte=timezone.now() - timedelta(hours=heures))
    return {"crees": sum(e.crees for e in qs), "signaux": sum(e.signaux for e in qs), "examines": sum(e.examines for e in qs),
            "erreurs": [f"{e.recherche.nom} : {e.erreur}" for e in qs if e.erreur]}
