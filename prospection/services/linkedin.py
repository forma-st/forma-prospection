"""Option LinkedIn (désactivée par défaut, Paramètres > « Activer l'option LinkedIn »).

Ce que fait le code, uniquement par les voies officielles de LinkedIn :
- connexion du compte de l'utilisateur (OAuth 2.0, produit « Sign In with LinkedIn using OpenID Connect ») ;
- publication d'un post sur son profil (produit « Share on LinkedIn », portée w_member_social), après validation ;
- préparation des invitations et messages, liens de recherche, plafonds et historique des actions faites à la main.

Ce que le code ne fait jamais : lire des profils, envoyer une invitation ou un message à la place de l'utilisateur
(interdit par les conditions d'utilisation de LinkedIn). Le copilote navigateur (Claude in Chrome) reste sous le contrôle
de l'utilisateur, qui clique lui-même sur « Envoyer ».

Réglages (.env) : LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, et en option LINKEDIN_API_VERSION (AAAAMM).
URL de redirection à déclarer dans l'application LinkedIn : {BASE_URL}/prospection/linkedin/retour/
"""

from __future__ import annotations

import os
import secrets
from datetime import timedelta
from urllib.parse import quote_plus, urlencode

import httpx
from django.conf import settings
from django.utils import timezone

from ..models import ActionLinkedIn, ConnexionLinkedIn, Parametres, PublicationLinkedIn

AUTORISATION = "https://www.linkedin.com/oauth/v2/authorization"
JETON = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO = "https://api.linkedin.com/v2/userinfo"
POSTS = "https://api.linkedin.com/rest/posts"
PORTEES = "openid profile email w_member_social"


class ErreurLinkedIn(Exception):
    pass


def configuree() -> bool:
    return bool(os.environ.get("LINKEDIN_CLIENT_ID") and os.environ.get("LINKEDIN_CLIENT_SECRET"))


def active() -> bool:
    return Parametres.get().linkedin_actif


def url_retour() -> str:
    return settings.BASE_URL.rstrip("/") + "/prospection/linkedin/retour/"


def version_api() -> str:
    """Version de l'API versionnée de LinkedIn (AAAAMM). Par défaut : il y a deux mois, pour rester dans la fenêtre prise en charge."""
    v = os.environ.get("LINKEDIN_API_VERSION")
    if v:
        return v
    d = timezone.localdate().replace(day=1) - timedelta(days=45)
    return d.strftime("%Y%m")


def url_autorisation(session) -> str:
    etat = secrets.token_urlsafe(24)
    session["linkedin_etat"] = etat
    return AUTORISATION + "?" + urlencode({
        "response_type": "code", "client_id": os.environ["LINKEDIN_CLIENT_ID"], "redirect_uri": url_retour(),
        "state": etat, "scope": PORTEES,
    })


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), headers={"User-Agent": "prospection-formast/1.0"})


def terminer_connexion(utilisateur, code: str, etat: str, session) -> ConnexionLinkedIn:
    attendu = session.pop("linkedin_etat", None)
    if not attendu or not secrets.compare_digest(attendu, etat or ""):
        raise ErreurLinkedIn("La demande de connexion a expiré ou ne vient pas de cette page. Recommencez.")
    with _client() as h:
        r = h.post(JETON, data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": url_retour(),
            "client_id": os.environ["LINKEDIN_CLIENT_ID"], "client_secret": os.environ["LINKEDIN_CLIENT_SECRET"],
        })
        if r.status_code != 200:
            raise ErreurLinkedIn(f"LinkedIn a refusé la connexion ({r.status_code}) : {r.text[:200]}")
        jeton = r.json()
        u = h.get(USERINFO, headers={"Authorization": f"Bearer {jeton['access_token']}"})
        if u.status_code != 200:
            raise ErreurLinkedIn(f"Impossible de lire votre identité LinkedIn ({u.status_code}).")
        info = u.json()
    cx, _ = ConnexionLinkedIn.objects.update_or_create(utilisateur=utilisateur, defaults={
        "sub": info["sub"], "nom": info.get("name", ""), "email": info.get("email", ""), "photo": info.get("picture", "") or "",
        "jeton": jeton["access_token"], "expire_le": timezone.now() + timedelta(seconds=int(jeton.get("expires_in", 5184000))),
        "portees": jeton.get("scope", PORTEES).replace(",", " "),
    })
    return cx


def publier(pub: PublicationLinkedIn) -> PublicationLinkedIn:
    cx = ConnexionLinkedIn.objects.filter(utilisateur=pub.utilisateur).first()
    if not cx or not cx.valide:
        raise ErreurLinkedIn("Votre compte LinkedIn n'est pas connecté, ou la connexion a expiré (60 jours). Reconnectez-le.")
    if not cx.peut_publier:
        raise ErreurLinkedIn("La connexion ne donne pas le droit de publier : ajoutez le produit « Share on LinkedIn » à l'application.")
    corps = {
        "author": f"urn:li:person:{cx.sub}", "commentary": pub.texte, "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False,
    }
    with _client() as h:
        r = h.post(POSTS, json=corps, headers={
            "Authorization": f"Bearer {cx.jeton}", "LinkedIn-Version": version_api(), "X-Restli-Protocol-Version": "2.0.0",
        })
    if r.status_code not in (200, 201):
        pub.statut, pub.erreur = "erreur", f"{r.status_code} : {r.text[:500]}"
        pub.save()
        raise ErreurLinkedIn(f"LinkedIn a refusé la publication ({r.status_code}). Détail enregistré sur la publication.")
    pub.statut, pub.urn, pub.erreur, pub.publiee_le = "publiee", r.headers.get("x-restli-id", ""), "", timezone.now()
    pub.save()
    return pub


def compteurs(utilisateur) -> dict:
    p = Parametres.get()
    maintenant = timezone.now()
    debut_jour = timezone.localtime(maintenant).replace(hour=0, minute=0, second=0, microsecond=0)
    qs = ActionLinkedIn.objects.filter(utilisateur=utilisateur)
    inv = qs.filter(type="invitation", cree_le__gte=maintenant - timedelta(days=7)).count()
    prof = qs.filter(type="profil", cree_le__gte=debut_jour).count()
    return {"invitations": inv, "invitations_max": p.linkedin_invitations_semaine,
            "profils": prof, "profils_max": p.linkedin_profils_jour,
            "invitations_atteint": inv >= p.linkedin_invitations_semaine, "profils_atteint": prof >= p.linkedin_profils_jour}


def recherche_personne(prenom: str, nom: str, entreprise: str) -> str:
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(f"{prenom} {nom} {entreprise}".strip())


def recherche_decideur(entreprise: str, fonction: str = "QSE OR RH OR sécurité") -> str:
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(f"{entreprise} {fonction}")


def recherche_entreprise(entreprise: str) -> str:
    return "https://www.linkedin.com/search/results/companies/?keywords=" + quote_plus(entreprise)


POSTS_PROPOSES = [
    "Combien de sauveteurs secouristes du travail faut-il dans votre entreprise ? L'INRS recommande 10 à 15 % de l'effectif, "
    "et un recyclage (MAC SST) tous les 24 mois. Un repère simple : 100 salariés, c'est 10 à 15 SST, soit deux sessions.",
    "Exercice d'évacuation : le Code du travail en demande un au moins tous les 6 mois. Ce que nous voyons le plus souvent "
    "sur le terrain : des serre-files non désignés et des points de rassemblement trop proches du bâtiment.",
    "Former 30 nouveaux salariés en deux semaines sans arrêter l'activité, c'est possible : sessions en horaires décalés, "
    "gestes et postures sur leurs propres postes, et une unité mobile incendie sur le parking.",
]

CONSIGNES_COPILOTE = """Tu m'aides à prospecter sur LinkedIn pour FORMA'ST (formation santé et sécurité au travail).
Règles strictes :
1. Tu ne cliques JAMAIS sur « Se connecter », « Envoyer », « Suivre » ni « Message » : je le fais moi-même.
2. Tu ne consultes que les pages que je t'indique, au rythme d'une page à la fois, et au plus 30 profils par jour.
3. Tu ne copies aucune donnée en masse. Tu me résumes seulement : poste actuel, ancienneté, changement de poste récent,
   publications récentes sur la sécurité, la formation ou le recrutement.
4. Tu prépares l'invitation (300 caractères au plus, sans lien) ou le message dans la zone de texte, puis tu t'arrêtes.
5. Tu n'inventes rien : si une information n'est pas visible, tu le dis."""
