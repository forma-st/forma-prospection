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


ICONES = {
    "journee": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "prospects": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c1.9.7 3.1 2.5 3.5 5.2"/>',
    "taches": '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M8 12.5l2.7 2.7L16 9.5"/>',
    "reponses": '<path d="M3.5 13.5l2.4-8h12.2l2.4 8v5a1.5 1.5 0 0 1-1.5 1.5h-14A1.5 1.5 0 0 1 3.5 18.5z"/><path d="M3.5 13.5h5l1.5 2.5h4l1.5-2.5h5"/>',
    "stats": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "import": '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
    "historique": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "sequences": '<path d="M5 6h14M5 12h10M5 18h6"/><circle cx="19" cy="18" r="2"/>',
    "messagerie": '<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="M3.5 7l8.5 6 8.5-6"/>',
    "linkedin": '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M8 10.5v6M8 7.5v.01M12 16.5v-3.5a2.5 2.5 0 0 1 5 0v3.5M12 10.5v6"/>',
    "opposition": '<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6z"/><path d="M9 12l2 2 4-4"/>',
    "parametres": '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    "catalogue": '<path d="M5 4h11l3 3v13H5z"/><path d="M9 10h6M9 14h6"/>',
    "utilisateurs": '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c.8-3.5 3.6-5.5 7-5.5s6.2 2 7 5.5"/>',
    "lien": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "recherche": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    "theme": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "appel": '<path d="M5 3.5h3.5l1.5 4.5-2.2 1.5a11 11 0 0 0 6.7 6.7L16 14l4.5 1.5V19a1.5 1.5 0 0 1-1.6 1.5A16.5 16.5 0 0 1 3.5 5.1 1.5 1.5 0 0 1 5 3.5z"/>',
    "email": '<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="M3.5 7l8.5 6 8.5-6"/>',
    "spark": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
}


@register.simple_tag
def icone(nom, classe=""):
    from django.utils.safestring import mark_safe
    return mark_safe(f'<svg class="ic {classe}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
                     f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONES.get(nom, ICONES["spark"])}</svg>')


@register.filter
def get_item(d, k):
    try:
        return d.get(k)
    except AttributeError:
        return None


@register.filter
def split_pairs(s):
    return [tuple(x.split(":", 1)) for x in s.split(",")]


@register.filter
def active_ce_mois(r):
    return r.active_ce_mois()
