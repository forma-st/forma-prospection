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
