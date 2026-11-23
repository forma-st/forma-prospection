from django import template

from .. import regles

register = template.Library()


@register.filter
def eur(v):
    try:
        return f"{round(float(v)):,} €".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


@register.filter
def signal_libelle(t):
    return regles.SIGNAUX.get(t, {}).get("libelle", t)


@register.filter
def segment_libelle(s):
    return regles.SEGMENTS.get(s, {}).get("libelle", s)


@register.filter
def classe_statut(st):
    return {"À qualifier": "warn", "À contacter": "info", "En contact": "info", "A répondu": "ok", "RDV fixé": "ok",
            "Transmis au CRM": "ok", "Client": "ok", "Pas maintenant": "warn", "Opposé": "bad"}.get(st, "")


@register.filter
def pct(v, maxi):
    try:
        return min(100, round(float(v) / max(1, float(maxi)) * 100))
    except (TypeError, ValueError):
        return 0


@register.inclusion_tag("prospection/_jauge.html")
def jauge(score, palier):
    import math
    r = 23
    c = 2 * math.pi * r
    return {"score": score, "palier": palier, "dash": f"{c * score / 100:.1f} {c:.1f}"}
