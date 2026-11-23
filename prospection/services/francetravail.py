"""API « Offres d'emploi v2 » de France Travail (accès gratuit, identifiants à créer sur francetravail.io).

Réglages (.env) : FRANCETRAVAIL_CLIENT_ID, FRANCETRAVAIL_CLIENT_SECRET.
Authentification OAuth2 « client credentials » ; le jeton (valable environ 25 minutes) est gardé en mémoire.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone as tz

import httpx

JETON_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
OFFRES_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
PORTEE = "api_offresdemploiv2 o2dsoffre"
TAILLE_PAGE = 150
_cache: dict = {}


class FranceTravailIndisponible(Exception):
    pass


def _env(nom: str) -> str:
    """Valeur du .env sans espaces ni guillemets parasites (copier-coller depuis le site)."""
    return os.environ.get(nom, "").strip().strip("\"'").strip()


def configure() -> bool:
    return bool(_env("FRANCETRAVAIL_CLIENT_ID") and _env("FRANCETRAVAIL_CLIENT_SECRET"))


def _cause(r) -> str:
    try:
        d = r.json()
        code, detail = d.get("error", ""), d.get("error_description", "")
    except ValueError:
        code, detail = "", r.text[:200]
    if code == "invalid_client":
        conseil = ("identifiant ou clé secrète refusés : recopiez-les depuis « Mes applications » sur francetravail.io "
                   "(sans espace ni guillemet), ou régénérez la clé secrète")
    elif code == "invalid_scope":
        conseil = ("l'application n'a pas accès à l'API « Offres d'emploi v2 » : dans « Mes applications », ouvrez votre application "
                   "et vérifiez qu'elle figure dans ses API ; sinon ajoutez-la depuis le catalogue (rubrique Offres d'emploi)")
    else:
        conseil = "vérifiez les identifiants et l'abonnement à l'API « Offres d'emploi v2 »"
    return f"France Travail refuse la connexion ({r.status_code}{', ' + code if code else ''}) : {conseil}." + (f" Détail : {detail}" if detail else "")


def jeton(client: httpx.Client | None = None) -> str:
    if _cache.get("jeton") and _cache.get("expire", 0) > time.time() + 60:
        return _cache["jeton"]
    if not configure():
        raise FranceTravailIndisponible("Identifiants France Travail absents : renseignez FRANCETRAVAIL_CLIENT_ID et FRANCETRAVAIL_CLIENT_SECRET dans le .env.")
    h = client or httpx.Client(timeout=30)
    r = h.post(JETON_URL, params={"realm": "/partenaire"}, data={
        "grant_type": "client_credentials", "client_id": _env("FRANCETRAVAIL_CLIENT_ID"),
        "client_secret": _env("FRANCETRAVAIL_CLIENT_SECRET"), "scope": PORTEE,
    })
    if r.status_code != 200:
        raise FranceTravailIndisponible(_cause(r))
    d = r.json()
    _cache.update(jeton=d["access_token"], expire=time.time() + int(d.get("expires_in", 1499)))
    return _cache["jeton"]


def offres(params: dict, max_offres: int = 600, client: httpx.Client | None = None) -> list[dict]:
    """Toutes les offres correspondant aux critères (par pages de 150, dans la limite de max_offres)."""
    h = client or httpx.Client(timeout=30)
    resultats, debut = [], 0
    while debut < max_offres:
        fin = min(debut + TAILLE_PAGE, max_offres) - 1
        r = h.get(OFFRES_URL, params={**params, "range": f"{debut}-{fin}"},
                  headers={"Authorization": f"Bearer {jeton(h)}", "Accept": "application/json"})
        if r.status_code == 204:
            break
        if r.status_code == 401:
            _cache.clear()
            raise FranceTravailIndisponible("Jeton France Travail refusé : réessayez ; si cela persiste, vérifiez l'abonnement à l'API.")
        if r.status_code not in (200, 206):
            raise FranceTravailIndisponible(f"France Travail a répondu {r.status_code} : {r.text[:200]}")
        lot = r.json().get("resultats", [])
        resultats += lot
        if r.status_code == 200 or len(lot) < TAILLE_PAGE:
            break
        debut += TAILLE_PAGE
    return resultats


def depuis(jours: int) -> str:
    return (datetime.now(tz.utc) - timedelta(days=jours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def maintenant() -> str:
    return datetime.now(tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ Diagnostic (découverte des API de l'application)

LBB_URL = "https://api.francetravail.io/partenaire/labonneboite/v2"
PORTEES_A_TESTER = [
    PORTEE,
    "api_labonneboitev2",
    "api_labonneboitev2 search office",
    "api_labonneboitev2 office",
    "api_labonneboitev2 search",
]
CHEMINS_LBB = ["", "/recherche", "/entreprises", "/search", "/companies", "/office", "/count", "/nombre",
               "/openapi.json", "/swagger.json", "/v3/api-docs"]
ESSAI_LBB = {"rome": "N1103", "romes": "N1103", "citycode": "95127", "commune": "95127", "distance": "30",
             "latitude": "49.0364", "longitude": "2.0761"}  # magasinage / Cergy


def diagnostic(client: httpx.Client | None = None) -> list[str]:
    """Teste chaque portée possible, puis interroge La Bonne Boîte pour en découvrir les chemins et les champs.
    Lecture seule ; n'affiche jamais la clé secrète ni le jeton."""
    h = client or httpx.Client(timeout=30)
    lignes = [f"Identifiant : {_env('FRANCETRAVAIL_CLIENT_ID')[:12]}… (clé secrète {'présente' if _env('FRANCETRAVAIL_CLIENT_SECRET') else 'ABSENTE'})"]
    if not configure():
        return lignes + ["Identifiants absents du .env : rien à tester."]
    jetons = {}
    for portee in PORTEES_A_TESTER:
        r = h.post(JETON_URL, params={"realm": "/partenaire"}, data={
            "grant_type": "client_credentials", "client_id": _env("FRANCETRAVAIL_CLIENT_ID"),
            "client_secret": _env("FRANCETRAVAIL_CLIENT_SECRET"), "scope": portee})
        if r.status_code == 200:
            d = r.json()
            jetons[portee] = d["access_token"]
            lignes.append(f"PORTÉE ACCEPTÉE  « {portee} » (accordée : « {d.get('scope', '?')} »)")
        else:
            try:
                code = r.json().get("error", "")
            except ValueError:
                code = ""
            lignes.append(f"portée refusée   « {portee} » ({r.status_code} {code})")
    lbb = next((j for p, j in jetons.items() if "labonneboite" in p), None)
    if not lbb:
        return lignes + ["Aucune portée La Bonne Boîte acceptée : copiez la portée exacte depuis la page de l'API (rubrique Authentification)."]
    for chemin in CHEMINS_LBB:
        try:
            r = h.get(LBB_URL + chemin, params=ESSAI_LBB, headers={"Authorization": f"Bearer {lbb}", "Accept": "application/json"})
        except httpx.HTTPError as e:
            lignes.append(f"GET {chemin or '/'} : erreur réseau {e.__class__.__name__}")
            continue
        corps = " ".join(r.text.split())
        lignes.append(f"GET {chemin or '/'} : {r.status_code} · {corps[:1500]}")
    return lignes
