"""Client HTTP commun avec reprises automatiques (réseau parfois instable)."""

import logging
import time

import httpx

log = logging.getLogger("veille.http")

_client = httpx.Client(
    timeout=httpx.Timeout(60.0, connect=20.0),
    headers={"User-Agent": "veille-ao/0.1 (internal tender monitoring tool)"},
    follow_redirects=True,
)

ESSAIS = 5


def _requete(methode: str, url: str, **kwargs) -> httpx.Response:
    derniere_erreur = None
    for essai in range(1, ESSAIS + 1):
        try:
            resp = _client.request(methode, url, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            statut = getattr(getattr(e, "response", None), "status_code", None)
            if statut is not None and statut not in (429, 500, 502, 503, 504):
                raise
            derniere_erreur = e
            attente = min(2**essai, 30)
            log.warning("%s %s : %s (essai %s/%s, nouvel essai dans %ss)", methode, url, e, essai, ESSAIS, attente)
            time.sleep(attente)
    raise derniere_erreur


def get_json(url: str, **kwargs):
    return _requete("GET", url, **kwargs).json()


def post_json(url: str, **kwargs):
    return _requete("POST", url, **kwargs).json()
