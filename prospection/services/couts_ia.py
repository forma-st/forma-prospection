"""Coûts de l'IA : suivi réel des appels, budget mensuel et simulateur.

Tarifs publics de l'API Claude (novembre 2026), en dollars par million de jetons.
Écriture en cache (5 min) : 1,25 × le prix d'entrée. À mettre à jour si Anthropic change ses prix.
Le montant exact reste celui de la facture Anthropic (console) : ici, c'est une estimation fidèle à quelques pour cent.
"""

from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

from ..models import AppelIA, Parametres

log = logging.getLogger("prospection.couts_ia")

# identifiant -> (libellé, entrée, sortie, lecture du cache)
TARIFS = {
    "claude-opus-5-5": ("Opus 5.5 (par défaut)", 4.00, 20.00, 0.20),
    "claude-sonnet-5-5": ("Sonnet 5.5", 2.00, 10.00, 0.10),
    "claude-haiku-5-5": ("Haiku 5.5", 0.10, 0.50, 0.01),
    "claude-fable-5-2": ("Fable 5.2", 8.00, 40.00, 0.20),
    "claude-opus-5": ("Opus 5", 5.00, 25.00, 0.50),
    "claude-sonnet-5": ("Sonnet 5", 2.00, 10.00, 0.20),
    "claude-opus-4-8": ("Opus 4.8", 5.00, 25.00, 0.50),
    "claude-haiku-4-5": ("Haiku 4.5", 1.00, 5.00, 0.10),
}
COMPARES = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
ECRITURE_CACHE = 1.25

# Tâches du simulateur : jetons moyens par appel (entrée, sortie), réflexion comprise dans la sortie.
TACHES = [
    {"cle": "redaction", "libelle": "E-mail ou relance amélioré par l'IA", "volume": 150, "entree": 2500, "sortie": 800,
     "aide": "Bouton « Améliorer avec l'IA » sur la fiche."},
    {"cle": "sequence", "libelle": "Étape de séquence personnalisée par l'IA", "volume": 0, "entree": 2500, "sortie": 800,
     "aide": "Option envisagée : chaque e-mail de séquence réécrit pour le prospect."},
    {"cle": "classement", "libelle": "Classement d'une réponse ambiguë", "volume": 0, "entree": 1500, "sortie": 150,
     "aide": "Option envisagée : quand les règles hésitent (« autre »)."},
    {"cle": "synthese", "libelle": "Synthèse de fiche ou d'article de presse", "volume": 0, "entree": 3000, "sortie": 500,
     "aide": "Option envisagée : veille presse, colonnes IA."},
]


def tarif(modele: str) -> tuple[str, float, float, float, bool]:
    """(libellé, entrée, sortie, cache lu, connu). Un modèle inconnu est compté au tarif du modèle par défaut."""
    for cle in sorted(TARIFS, key=len, reverse=True):
        if modele == cle or modele.startswith(cle + "-"):
            return (*TARIFS[cle], True)
    return (modele or "inconnu", *TARIFS["claude-opus-5-5"][1:], False)


def cout_usd(modele: str, entree: int = 0, sortie: int = 0, cache_ecrits: int = 0, cache_lus: int = 0) -> float:
    _, e, s, cl, _ = tarif(modele)
    return (entree * e + sortie * s + cache_ecrits * e * ECRITURE_CACHE + cache_lus * cl) / 1_000_000


def taux() -> float:
    return float(Parametres.get().taux_usd_eur)


def enregistrer(rep, usage: str = "autre", compte=None, utilisateur=None) -> AppelIA | None:
    """Enregistre la consommation d'une réponse de l'API (rep.model, rep.usage). Ne bloque jamais l'appelant."""
    try:
        u = rep.usage
        modele = getattr(rep, "model", "") or settings.CLAUDE_MODEL
        n = {k: int(getattr(u, k, 0) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
        return AppelIA.objects.create(
            usage=usage, modele=str(modele)[:60], tokens_entree=n["input_tokens"], tokens_sortie=n["output_tokens"],
            tokens_cache_ecrits=n["cache_creation_input_tokens"], tokens_cache_lus=n["cache_read_input_tokens"],
            cout_usd=Decimal(str(round(cout_usd(modele, n["input_tokens"], n["output_tokens"], n["cache_creation_input_tokens"],
                                                n["cache_read_input_tokens"]), 6))),
            compte=compte, utilisateur=utilisateur if getattr(utilisateur, "is_authenticated", False) else None)
    except Exception as e:  # le suivi ne doit jamais faire échouer la rédaction
        log.warning("Consommation IA non enregistrée : %s", e)
        return None


def _debut_mois(jour=None):
    jour = jour or timezone.localdate()
    return timezone.make_aware(datetime(jour.year, jour.month, 1))


def mois_en_cours() -> dict:
    p = Parametres.get()
    t = float(p.taux_usd_eur)
    qs = AppelIA.objects.filter(cree_le__gte=_debut_mois())
    total_usd = float(qs.aggregate(s=Sum("cout_usd"))["s"] or 0)
    jour = timezone.localdate()
    nb_jours = calendar.monthrange(jour.year, jour.month)[1]
    total_eur = total_usd * t
    projection = total_eur / jour.day * nb_jours
    budget = p.budget_ia_mensuel
    pct = round(total_eur / budget * 100) if budget else 0
    libelles = dict(AppelIA.USAGES)
    par_usage = [{"usage": libelles.get(r["usage"], r["usage"]), "nb": r["nb"], "eur": float(r["s"] or 0) * t}
                 for r in qs.values("usage").annotate(nb=Count("id"), s=Sum("cout_usd")).order_by("-s")]
    return {"usd": total_usd, "eur": total_eur, "nb": qs.count(), "projection": projection, "budget": budget, "pct": pct,
            "etat": "depasse" if budget and pct >= 100 else "proche" if budget and pct >= 80 else "ok",
            "par_usage": par_usage, "moyen": total_eur / qs.count() if qs.count() else 0, "bloque": p.bloquer_ia_au_budget}


def budget_atteint() -> bool:
    p = Parametres.get()
    return bool(p.bloquer_ia_au_budget and p.budget_ia_mensuel and mois_en_cours()["eur"] >= p.budget_ia_mensuel)


def moyennes(minimum: int = 3) -> dict:
    """Jetons moyens réellement observés par usage (90 derniers jours), quand il y a assez d'appels."""
    depuis = timezone.now() - timedelta(days=90)
    res = {}
    for r in (AppelIA.objects.filter(cree_le__gte=depuis).values("usage")
              .annotate(nb=Count("id"), e=Sum("tokens_entree"), ce=Sum("tokens_cache_ecrits"), cl=Sum("tokens_cache_lus"), s=Sum("tokens_sortie"))):
        if r["nb"] >= minimum:
            res[r["usage"]] = {"nb": r["nb"], "entree": round((r["e"] + r["ce"] + r["cl"]) / r["nb"]), "sortie": round(r["s"] / r["nb"])}
    return res


def simuler(lignes: list[dict], modele: str, taux_eur: float, prospects: int = 0, budget: int = 0) -> dict:
    """lignes : [{cle, libelle, volume, entree, sortie}] -> coût par appel et par mois, comparaison entre modèles."""
    detail, total_usd = [], 0.0
    for l in lignes:
        unitaire = cout_usd(modele, l["entree"], l["sortie"])
        mensuel = unitaire * l["volume"]
        total_usd += mensuel
        detail.append({**l, "unitaire_eur": unitaire * taux_eur, "mensuel_eur": mensuel * taux_eur})
    comparaison = []
    for m in dict.fromkeys(COMPARES + [modele]):
        usd = sum(cout_usd(m, l["entree"], l["sortie"]) * l["volume"] for l in lignes)
        comparaison.append({"modele": m, "libelle": tarif(m)[0], "mensuel_eur": usd * taux_eur, "annuel_eur": usd * taux_eur * 12,
                            "choisi": m == modele})
    total_eur = total_usd * taux_eur
    return {"lignes": detail, "mensuel_eur": total_eur, "annuel_eur": total_eur * 12, "usd": total_usd,
            "par_prospect": total_eur / prospects if prospects else None, "appels": sum(l["volume"] for l in lignes),
            "pct_budget": round(total_eur / budget * 100) if budget else None, "comparaison": comparaison}
