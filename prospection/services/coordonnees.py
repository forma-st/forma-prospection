"""Recherche approfondie des coordonnées d'un prospect.

Dans l'ordre, sans jamais écraser une donnée saisie :
1. Annuaire officiel des entreprises : adresse du siège, dirigeants (nom et fonction, données publiques du registre) ;
2. Site web de l'entreprise : celui de la fiche, sinon le domaine des e-mails connus, sinon un domaine deviné à partir du nom,
   retenu seulement si ses pages citent le SIREN ou le nom ; on y lit le téléphone et un e-mail générique (contact@, accueil@…)
   sur l'accueil, la page contact et les mentions légales ;
3. En option, Google Places (clé GOOGLE_PLACES_API_KEY dans le .env) : standard téléphonique, site et adresse.
Seules des coordonnées génériques de l'entreprise sont collectées sur le web : jamais d'e-mail nominatif, jamais LinkedIn.
"""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

import httpx
from django.utils import timezone

from ..models import Activite, Compte, Contact
from .http import get_json
from .rgpd import est_oppose
from .scoring import recalculer
from .sirene import URL as URL_SIRENE
from .texte import normaliser

log = logging.getLogger("prospection.coordonnees")

URL_PLACES = "https://places.googleapis.com/v1/places:searchText"
TELEPHONE = re.compile(r"(?<![\d+])(?:\+33\s?\(?0?\)?\s?|0)([1-9])(?:[\s.\-]?(\d{2})){4}(?!\d)")
EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)
GENERIQUES = ("contact", "accueil", "info", "infos", "standard", "secretariat", "direction", "rh", "drh", "recrutement", "qse", "qhse",
              "hse", "securite", "commercial", "administration", "bonjour", "hello", "siege", "formation")
WEBMAILS = ("gmail.", "hotmail.", "outlook.", "yahoo.", "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr", "laposte.net", "icloud.", "live.")
FONCTIONS_DIRIGEANTS = ("président", "president", "directeur général", "directeur general", "gérant", "gerant", "directrice générale")
FORMES = r"\b(sas|sasu|sarl|sa|eurl|sci|snc|scop|groupe|group|france|et cie|cie|societe|ste|ets|etablissements)\b"
PAGES = ("contact", "nous-contacter", "contactez-nous", "mentions-legales", "mentions", "legal", "a-propos", "qui-sommes-nous")


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(8.0, connect=5.0), follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; forma-prospect/1.0; outil interne)", "Accept-Language": "fr"})


def format_tel(brut: str) -> str:
    chiffres = re.sub(r"\D", "", brut)
    if chiffres.startswith("33"):
        chiffres = "0" + chiffres[2:].lstrip("0")
    return " ".join(chiffres[i:i + 2] for i in range(0, 10, 2)) if len(chiffres) == 10 else ""


def extraire(html: str, domaine: str = "") -> tuple[list[str], list[str]]:
    """(téléphones, e-mails génériques) trouvés dans une page. Les liens tel: et mailto: passent en premier."""
    tels = [format_tel(t) for t in re.findall(r'href=["\']tel:([^"\']+)', html, re.I)]
    texte = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    texte = re.sub(r"<[^>]+>", " ", texte)
    tels += [format_tel(m.group(0)) for m in TELEPHONE.finditer(texte)]
    mails = re.findall(r'href=["\']mailto:([^"\'?]+)', html, re.I) + EMAIL.findall(texte)
    garde = []
    for m in mails:
        m = m.strip().lower()
        local, _, dom = m.partition("@")
        if dom.endswith((".png", ".jpg", ".svg", ".webp", ".gif")) or local not in GENERIQUES:
            continue
        if domaine and not dom.endswith(domaine):
            continue
        garde.append(m)
    uniq = lambda xs: list(dict.fromkeys(x for x in xs if x))  # noqa: E731
    tels = uniq(tels)
    # fixes (01-05, 09) avant les mobiles
    return sorted(tels, key=lambda t: t[:2] in ("06", "07")), uniq(garde)


def _domaine(url: str) -> str:
    d = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    return d[4:] if d.startswith("www.") else d


def domaines_candidats(c: Compte) -> list[str]:
    """Site de la fiche, puis domaine des e-mails professionnels connus, puis domaines devinés à partir du nom."""
    res = []
    if c.site_web:
        res.append(_domaine(c.site_web))
    for k in c.contacts.all():
        dom = k.email.partition("@")[2].lower() if k.email else ""
        if dom and not any(w in dom for w in WEBMAILS):
            res.append(dom)
    base = re.sub(FORMES, " ", normaliser(c.nom))
    mots = re.findall(r"[a-z0-9]+", base)
    if mots:
        for slug in dict.fromkeys(["".join(mots), "-".join(mots)]):
            if 3 <= len(slug) <= 40:
                res += [f"{slug}.fr", f"{slug}.com"]
    return list(dict.fromkeys(res))


def lire_site(c: Compte, domaine: str, client: httpx.Client, verifier: bool = True) -> dict | None:
    """Lit l'accueil et les pages contact / mentions légales. Si verifier, le site doit citer le SIREN ou le nom."""
    pages, base = [], None
    for prefixe in ("https://www.", "https://"):
        try:
            r = client.get(f"{prefixe}{domaine}/")
        except httpx.HTTPError:
            continue
        if r.status_code == 200 and "html" in r.headers.get("content-type", "html"):
            base, pages = str(r.url), [r.text[:400_000]]
            break
    if not base:
        return None
    liens = re.findall(r'href=["\']([^"\'#]+)["\']', pages[0], re.I)
    suivants = [urljoin(base, l) for l in liens if any(p in l.lower() for p in PAGES)]
    for url in list(dict.fromkeys(u for u in suivants if _domaine(u) == _domaine(base)))[:3]:
        try:
            r = client.get(url)
            if r.status_code == 200:
                pages.append(r.text[:400_000])
        except httpx.HTTPError:
            pass
    tout = "\n".join(pages)
    if verifier:
        siren_ok = c.siren and re.search(r"\b" + r"\s?".join(re.findall(r"\d{3}", c.siren)) + r"\b", tout)
        titre = re.search(r"<title[^>]*>(.*?)</title>", pages[0], re.S | re.I)
        nom = re.sub(FORMES, " ", normaliser(c.nom)).strip()
        nom_ok = nom and len(nom) >= 4 and nom in normaliser(titre.group(1) if titre else "")
        if not (siren_ok or nom_ok):
            return None
    tels, mails = extraire(tout, _domaine(base))
    return {"site": base.rstrip("/") + "/", "telephone": tels[0] if tels else "", "email": mails[0] if mails else ""}


def places(c: Compte, client: httpx.Client) -> dict | None:
    cle = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if not cle:
        return None
    r = client.post(URL_PLACES, json={"textQuery": f"{c.nom} {c.adresse or c.ville or c.code_postal}", "languageCode": "fr", "regionCode": "FR"},
                    headers={"X-Goog-Api-Key": cle,
                             "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri"})
    if r.status_code != 200:
        log.warning("Google Places : %s %s", r.status_code, r.text[:200])
        return None
    p = (r.json().get("places") or [None])[0]
    if not p:
        return None
    nom = re.sub(FORMES, " ", normaliser(c.nom)).split()
    trouve = normaliser((p.get("displayName") or {}).get("text", ""))
    if nom and nom[0] not in trouve:  # résultat sans rapport avec l'entreprise
        return None
    return {"telephone": format_tel(p.get("nationalPhoneNumber", "")), "site": p.get("websiteUri", ""), "adresse": p.get("formattedAddress", "")}


def _sirene(c: Compte) -> dict | None:
    if not c.siren:
        return None
    data = get_json(URL_SIRENE, params={"q": c.siren, "per_page": 1})
    return next((x for x in data.get("results", []) if x.get("siren") == c.siren), None)


def enrichir(c: Compte, utilisateur=None, client: httpx.Client | None = None) -> list[str]:
    """Complète la fiche. Renvoie la liste de ce qui a été trouvé (vide si rien)."""
    client = client or _client()
    trouve: list[str] = []
    # 1. annuaire officiel
    try:
        res = _sirene(c)
    except Exception as e:
        log.warning("Annuaire indisponible pour %s : %s", c, e)
        res = None
    if res:
        siege = res.get("siege") or {}
        if siege.get("adresse") and not c.adresse:
            c.adresse = siege["adresse"].title().replace(" Cedex", " CEDEX")[:255]
            trouve.append("adresse du siège")
        existants = {normaliser(k.nom_complet) for k in c.contacts.all()}
        n = 0
        for d in res.get("dirigeants") or []:
            q = (d.get("qualite") or "").strip()
            if d.get("type_dirigeant") != "personne physique" or not any(f in q.lower() for f in FONCTIONS_DIRIGEANTS) or n >= 2:
                continue
            prenom = (d.get("prenoms") or "").split(" ")[0].title()
            nom = (d.get("nom") or "").title()
            if not nom or normaliser(f"{prenom} {nom}") in existants:
                continue
            Contact.objects.create(compte=c, prenom=prenom, nom=nom, fonction=q, role="decideur" if c.effectif < 250 else "prescripteur")
            trouve.append(f"dirigeant : {prenom} {nom} ({q})")
            n += 1
    # 2. site web
    site = None
    for i, dom in enumerate(domaines_candidats(c)):
        connu = i == 0 and bool(c.site_web)
        site = lire_site(c, dom, client, verifier=not connu)
        if site:
            break
        time.sleep(0.2)
    # 3. Google Places (facultatif) si le site n'a pas donné de téléphone
    gp = None
    if not (site and site["telephone"]):
        try:
            gp = places(c, client)
        except httpx.HTTPError as e:
            log.warning("Google Places indisponible : %s", e)
        if gp and gp.get("site") and not site:
            site = lire_site(c, _domaine(gp["site"]), client, verifier=False)
    if site and not c.site_web:
        c.site_web = site["site"][:200]
        trouve.append(f"site web : {c.site_web}")
    if gp and gp.get("adresse") and not c.adresse:
        c.adresse = gp["adresse"][:255]
        trouve.append("adresse")
    tel = (site or {}).get("telephone") or (gp or {}).get("telephone") or ""
    mail = (site or {}).get("email") or ""
    if mail and est_oppose(mail):
        mail = ""
    if tel or mail:
        std = c.contacts.filter(role="standard").first() or Contact(compte=c, nom="Standard", fonction="Accueil", role="standard")
        if tel and not std.telephone:
            std.telephone = tel
            trouve.append(f"standard : {tel}")
        if mail and not std.email:
            std.email, std.statut_email = mail, "probable"
            trouve.append(f"e-mail générique : {mail}")
        if std.telephone or std.email:
            std.save()
    c.coordonnees_le = timezone.now()
    c.save()
    sources = "annuaire" + (", site web" if site else "") + (", Google" if gp else "")
    Activite.objects.create(compte=c, type="systeme", utilisateur=utilisateur,
                            texte=(f"Coordonnées trouvées ({sources}) : " + " ; ".join(trouve)) if trouve else "Recherche de coordonnées : rien de nouveau.")
    recalculer(c)
    return trouve


def enrichir_lot(maximum: int = 30) -> dict:
    """Traitement du matin : prospects actifs les mieux notés, sans standard téléphonique, jamais recherchés (ou il y a plus de 90 jours)."""
    from datetime import timedelta

    from django.db.models import Q

    from .. import regles
    limite = timezone.now() - timedelta(days=90)
    qs = (Compte.objects.exclude(statut__in=regles.STATUTS_INACTIFS).filter(Q(coordonnees_le__isnull=True) | Q(coordonnees_le__lt=limite))
          .exclude(contacts__role="standard", contacts__telephone__gt="").order_by("-score")[:maximum])
    bilan = {"examines": 0, "completes": 0, "erreurs": 0}
    client = _client()
    for c in qs:
        bilan["examines"] += 1
        try:
            if enrichir(c, client=client):
                bilan["completes"] += 1
        except Exception as e:  # un site injoignable ne bloque pas le lot
            bilan["erreurs"] += 1
            log.warning("Coordonnées de %s : %s", c, e)
            Compte.objects.filter(pk=c.pk).update(coordonnees_le=timezone.now())
    return bilan
