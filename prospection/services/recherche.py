"""Recherche automatique de prospects (cahier des charges §3.1, phase 3).

Chaque nuit, chaque recherche active interroge une source publique gratuite, filtre selon la cible, écarte les doublons,
les clients, les opposés et les entreprises fermées, calcule le score et ne garde que les prospects au-dessus du palier
minimum. Les nouveaux prospects arrivent « À qualifier » : rien n'est contacté sans validation.

Sources :
- sirene     : API Recherche d'entreprises (DINUM) — entreprises correspondant à la cible (NAF, départements, effectif) ;
- bodacc     : annonces BODACC de création d'établissement — signal « nouvel établissement » ;
- georisques : installations classées (ICPE) — sites industriels à fort besoin incendie / évacuation ;
- francetravail : offres d'emploi (recrutements QSE ou en nombre) ;
- labonneboite : entreprises à fort potentiel d'embauche dans les 6 mois (France Travail), par métier ROME et par département.

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


INTERIM = re.compile(r"\b(adecco|manpower|randstad|synergie|crit|start people|proman|samsic emploi|partnaire|interim|int[ée]rim|supplay|gojob|staffmatch|temporis|actual)\b", re.I)


def _entreprise_offre(o: dict) -> tuple[str, str, str]:
    e = o.get("entreprise") or {}
    lieu = o.get("lieuTravail") or {}
    cp = (lieu.get("codePostal") or "").strip()
    dep = cp[:2] if cp else (lieu.get("libelle") or "")[:2]
    return (e.get("nom") or "").strip(), cp, dep if dep.isdigit() or dep in ("2A", "2B") else ""


def _sirene_par_nom(nom: str, cp: str, dep: str) -> dict | None:
    from .sirene import chercher
    temp = Compte(nom=nom, code_postal=cp, departement=dep)
    res, confiance = chercher(temp)
    time.sleep(PAUSE)
    return res if res and confiance >= 80 else None


def chercher_francetravail(r: RechercheAuto, ex: ExecutionRecherche, jours: int = 7) -> None:
    """Deux usages : avec des mots-clés (offres QSE / HSE → signal « recrutement QSE »),
    ou sans mot-clé, par secteur (beaucoup d'offres dans la même entreprise → signal « recrutement en nombre »)."""
    from . import francetravail as ft

    base = {"minCreationDate": ft.depuis(jours), "maxCreationDate": ft.maintenant()}
    requetes = []
    deps = r.liste_departements() or [""]
    if r.mots_cles.strip():
        for dep in deps:
            requetes.append({**base, "motsCles": ",".join(m.strip() for m in r.mots_cles.replace("\n", ",").split(",") if m.strip())[:255],
                             **({"departement": dep} if dep else {})})
    else:
        divisions = sorted({n.replace(".", "")[:2] for n in r.liste_naf() if n[:2].isdigit()})
        for div in divisions or [""]:
            for dep in deps:
                requetes.append({**base, **({"secteurActivite": div} if div else {}), **({"departement": dep} if dep else {})})
    par_entreprise: dict[str, list[dict]] = {}
    vues: set[str] = set()
    for q in requetes:
        for o in ft.offres(q):
            if o.get("id") in vues:  # la même offre peut revenir dans plusieurs requêtes
                continue
            vues.add(o.get("id"))
            nom, cp, dep = _entreprise_offre(o)
            if not nom or INTERIM.search(nom) or (o.get("codeNAF") or "").startswith("78"):
                continue
            par_entreprise.setdefault(normaliser(nom), []).append(o)
    seuil = 1 if r.mots_cles.strip() else max(2, r.seuil_offres)
    for liste in sorted(par_entreprise.values(), key=len, reverse=True):
        if ex.crees >= r.max_par_nuit:
            break
        ex.examines += 1
        if len(liste) < seuil:
            ex.ignores += 1
            continue
        o = liste[0]
        nom, cp, dep = _entreprise_offre(o)
        if r.mots_cles.strip():
            type_, texte = "qse", f"Offre d'emploi « {o.get('intitule', '')[:120]} » ({(o.get('lieuTravail') or {}).get('libelle', '')})"
        else:
            type_, texte = "recrut", f"{len(liste)} offres d'emploi publiées en {jours} jours (dont « {o.get('intitule', '')[:80]} »)"
        url = (o.get("origineOffre") or {}).get("urlOrigine") or (f"https://candidat.francetravail.fr/offres/recherche/detail/{o['id']}" if o.get("id") else "")
        d = (o.get("dateCreation") or "")[:10]
        signal = (type_, texte, "France Travail", url, date.fromisoformat(d) if d else None)
        existant = _existe("", nom)
        if existant:
            if not existant.signaux.filter(type=type_, source="France Travail", date_signal=signal[4] or timezone.localdate()).exists():
                Signal.objects.create(compte=existant, type=type_, texte=texte[:300], source="France Travail", url=url, date_signal=signal[4] or timezone.localdate())
                recalculer(existant)
                ex.signaux += 1
            continue
        res = _sirene_par_nom(nom, cp, dep)
        if not res:
            ex.ignores += 1
            continue
        existant = Compte.objects.filter(siren=res.get("siren", "")).first()
        if existant:
            Signal.objects.create(compte=existant, type=type_, texte=texte[:300], source="France Travail", url=url, date_signal=signal[4] or timezone.localdate())
            recalculer(existant)
            ex.signaux += 1
            continue
        if not _filtre_entreprise(res, r):
            ex.ignores += 1
            continue
        _creer_depuis_sirene(res, r, ex, signal)


DEPARTEMENTS = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B", "971", "972", "973", "974", "976"]
URL_GEO = "https://geo.api.gouv.fr/communes"
DISTANCE_LBB = 50  # km autour de la commune la plus peuplée du département
_centres: dict[str, dict] = {}


def centre_departement(dep: str) -> dict | None:
    """Commune la plus peuplée du département (code INSEE et coordonnées), pour centrer la recherche La Bonne Boîte."""
    if dep not in _centres:
        communes = get_json(URL_GEO, params={"codeDepartement": dep, "fields": "code,nom,centre,population", "format": "json"}) or []
        time.sleep(PAUSE)
        c = max((x for x in communes if x.get("centre")), key=lambda x: x.get("population") or 0, default=None)
        if not c:
            return None
        lon, lat = c["centre"]["coordinates"]
        _centres[dep] = {"citycode": c["code"], "nom": c.get("nom", ""), "latitude": lat, "longitude": lon}
    return _centres[dep]


ROME = re.compile(r"\b[A-N]\d{4}\b")


def _naf_pointe(naf: str) -> str:
    n = (naf or "").replace(".", "").upper()
    return f"{n[:2]}.{n[2:]}" if len(n) == 5 else n


def chercher_labonneboite(r: RechercheAuto, ex: ExecutionRecherche) -> None:
    """Entreprises qui devraient recruter dans les 6 mois sur des métiers exposés (manutention, production, soins…) :
    signal « recrutements à venir ». Parcours des départements par lots, d'une nuit à l'autre."""
    from . import francetravail as ft

    romes = ROME.findall(r.mots_cles.upper())
    if not romes:
        raise ValueError("Indiquez au moins un code métier ROME dans « Mots-clés » (ex. N1103 pour le magasinage).")
    deps = r.liste_departements() or DEPARTEMENTS
    debut = (r.page_suivante - 1) % len(deps)
    lot = [deps[(debut + i) % len(deps)] for i in range(min(PAGES_PAR_NUIT, len(deps)))]
    r.page_suivante = (debut + len(lot)) % len(deps) + 1
    vus: dict[str, dict] = {}
    for dep in lot:
        centre = centre_departement(dep)
        if not centre:
            continue
        for rome in romes:
            for e in ft.labonneboite({"rome": rome, "citycode": centre["citycode"], "latitude": centre["latitude"],
                                      "longitude": centre["longitude"], "distance": DISTANCE_LBB}):
                siret = str(e.get("siret") or "")
                if len(siret) == 14 and (siret not in vus or (e.get("hiring_potential") or 0) > (vus[siret].get("hiring_potential") or 0)):
                    vus[siret] = e
            time.sleep(PAUSE)
    for e in sorted(vus.values(), key=lambda x: x.get("hiring_potential") or 0, reverse=True):
        if ex.crees >= r.max_par_nuit:
            break
        ex.examines += 1
        mini, maxi = e.get("headcount_min") or 0, e.get("headcount_max") or 0
        if (maxi and maxi < r.effectif_min) or (r.effectif_max and mini > r.effectif_max) \
                or not correspond_naf(_naf_pointe(e.get("naf", "")), r.liste_naf()) or (e.get("naf") or "").startswith("78"):
            ex.ignores += 1
            continue
        siren = e["siret"][:9]
        texte = (f"{'Très fort' if e.get('is_high_potential') else 'Fort'} potentiel d'embauche dans les 6 mois "
                 f"(métier {e.get('rome', '')}, établissement de {e.get('city', '?')})")
        signal = ("recrut", texte, "La Bonne Boîte", "https://labonneboite.francetravail.fr/", None)
        existant = _existe(siren, e.get("company_name", ""))
        if existant:
            depuis = timezone.localdate() - timedelta(days=60)
            if not existant.signaux.filter(source="La Bonne Boîte", date_signal__gte=depuis).exists():
                Signal.objects.create(compte=existant, type="recrut", texte=texte[:300], source="La Bonne Boîte", url=signal[3])
                recalculer(existant)
                ex.signaux += 1
            continue
        res = _sirene_par_siren(siren)
        if not res or not _filtre_entreprise(res, r):
            ex.ignores += 1
            continue
        _creer_depuis_sirene(res, r, ex, signal)


SOURCES = {"sirene": chercher_sirene, "bodacc": chercher_bodacc, "georisques": chercher_georisques, "francetravail": chercher_francetravail,
           "labonneboite": chercher_labonneboite}


def executer(r: RechercheAuto) -> ExecutionRecherche:
    ex = ExecutionRecherche.objects.create(recherche=r)
    try:
        SOURCES[r.source](r, ex)
    except Exception as e:  # une source en panne ne bloque pas les autres
        log.warning("Recherche « %s » : %s", r, e)
        ex.erreur = f"{e.__class__.__name__} : {e}"[:1000]
        if "invalid_scope" in str(e):  # l'application France Travail n'a pas accès à cette API : inutile de réessayer chaque nuit
            r.actif = False
            ex.erreur = (f"Recherche désactivée : votre application France Travail n'a pas accès à cette API. {ex.erreur}")[:1000]
    r.derniere_execution = timezone.now()
    r.save(update_fields=["page_suivante", "derniere_execution", "actif"])
    ex.save()
    return ex


def disponible(r: RechercheAuto) -> bool:
    if r.source in ("francetravail", "labonneboite"):
        from .francetravail import configure
        return configure()
    return True


def executer_tout(forcer: bool = False) -> list[ExecutionRecherche]:
    """Les recherches France Travail sont ignorées tant que les identifiants ne sont pas renseignés."""
    return [executer(r) for r in RechercheAuto.objects.filter(actif=True) if (forcer or r.active_ce_mois()) and disponible(r)]


def bilan_nuit(heures: int = 24) -> dict:
    qs = ExecutionRecherche.objects.filter(debut__gte=timezone.now() - timedelta(hours=heures))
    return {"crees": sum(e.crees for e in qs), "signaux": sum(e.signaux for e in qs), "examines": sum(e.examines for e in qs),
            "erreurs": [f"{e.recherche.nom} : {e.erreur}" for e in qs if e.erreur]}
