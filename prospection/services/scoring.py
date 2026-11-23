"""Score de priorité et besoin estimé (cahier des charges §3.2.3 et §3.3).

Mêmes formules que la maquette : adéquation, intention (signaux avec décroissance), accessibilité.
"""

from __future__ import annotations

import math

from .. import regles
from ..models import Compte, Parametres


def _arrondi(x: float) -> int:
    return int(math.floor(x + 0.5))


def valeur_signal(s) -> float:
    d = regles.SIGNAUX.get(s.type)
    if not d:
        return 0.0
    return d["poids"] * 0.5 ** (s.age_jours / d["demi_vie"])


def score_adequation(c: Compte, p: Parametres) -> int:
    s = regles.SEGMENTS.get(c.segment, regles.SEGMENTS["autre"])["poids"]
    e = c.effectif or 0
    s += 30 if 50 <= e <= 1000 else 22 if e > 1000 else 18 if e >= 20 else 5
    s += 15 if c.nb_etablissements > 10 else 10 if c.nb_etablissements > 1 else 0
    s += 15 if c.departement in p.departements() else 5
    s += (10 if c.icpe else 0) + (5 if c.erp else 0)
    return min(100, s)


def score_intention(c: Compte) -> int:
    total = sum(valeur_signal(s) for s in c.signaux.all() if s.actif)
    return min(100, _arrondi(total * 1.6))


def score_accessibilite(c: Compte) -> int:
    cs = c.contacts_actifs()
    s = 0
    if any(x.role == "decideur" for x in cs):
        s += 40
    elif any(x.role == "prescripteur" for x in cs):
        s += 20
    if any(x.statut_email == "verifie" and x.email and x.role != "standard" for x in cs):
        s += 30
    elif any(x.statut_email == "probable" and x.email for x in cs):
        s += 15
    if any(x.telephone for x in cs):
        s += 15
    if c.est_client:
        s += 15
    return min(100, s)


def besoin(c: Compte, part_sst: int | None = None) -> dict:
    part = part_sst if part_sst is not None else Parametres.get().part_sst
    t = tarifs()
    sst = math.ceil((c.effectif or 0) * part / 100)
    s_sess = math.ceil(sst / 10)
    gp_n = _arrondi((c.effectif or 0) * regles.SEGMENTS.get(c.segment, regles.SEGMENTS["autre"])["manutention"])
    g_sess = math.ceil(gp_n / 10)
    exo = 2 * max(1, min(c.nb_etablissements or 1, 20))
    an1 = s_sess * t["sst"] + g_sess * t["gp"] + exo * t["incendie"]
    rec = math.ceil(s_sess / 2) * t["sst"] * 0.55 + exo * t["incendie"]
    deja = c.decouverte.get("sst") if isinstance(c.decouverte, dict) else None
    ecart = max(0, sst - int(deja)) if str(deja or "").isdigit() else None
    return {
        "sst": sst, "sessions_sst": s_sess, "manutention": gp_n, "sessions_gp": g_sess, "exercices": exo,
        "potentiel_an1": _arrondi(an1), "recurrent": _arrondi(rec), "opco_finance": (c.effectif or 0) < 50,
        "part_sst": part, "tarifs": t, "ecart_sst": ecart,
    }


def tarifs() -> dict:
    """Tarifs intra du catalogue de l'outil AO, sinon tarifs d'exemple."""
    from ..models import Prestation

    t = dict(regles.TARIFS_DEFAUT)
    trouves, exemple = set(), False
    for pr in Prestation.objects.filter(actif=True, usage_potentiel__in=["sst", "gp", "incendie"]).order_by("exemple", "pk"):
        if pr.usage_potentiel not in trouves and pr.prix_intra_ht is not None:
            t[pr.usage_potentiel] = float(pr.prix_intra_ht)
            trouves.add(pr.usage_potentiel)
            exemple = exemple or pr.exemple
    t["source"] = "catalogue" if trouves and not exemple else "exemple"
    return t


def explication(c: Compte, palier: str) -> str:
    seg = regles.SEGMENTS.get(c.segment, regles.SEGMENTS["autre"])["libelle"].lower()
    parts = [f"{seg}, {c.effectif} salariés" + (f" sur {c.nb_etablissements} sites" if c.nb_etablissements > 1 else "")
             + (", site ICPE" if c.icpe else "") + (", ERP" if c.erp else "")]
    g = c.signal_principal()
    if g:
        age = "moins d'un jour" if g.age_jours == 0 else f"{g.age_jours} j"
        parts.append(f"{regles.SIGNAUX[g.type]['libelle'].lower()} il y a {age}")
    else:
        parts.append("aucun signal récent")
    k = c.contact_principal()
    if k:
        mail = {"verifie": ", e-mail vérifié", "probable": ", e-mail probable"}.get(k.statut_email, ", sans e-mail")
        parts.append(f"{'décideur' if k.role == 'decideur' else 'contact'} identifié ({(k.fonction or 'fonction inconnue').lower()}){mail}")
    else:
        parts.append("aucun contact identifié")
    return f"Palier {palier} : " + " ; ".join(parts) + "."


def recalculer(c: Compte, p: Parametres | None = None, enregistrer: bool = True) -> Compte:
    p = p or Parametres.get()
    f, i, a = score_adequation(c, p), score_intention(c), score_accessibilite(c)
    tot_poids = max(1, p.poids_adequation + p.poids_intention + p.poids_accessibilite)
    t = _arrondi((p.poids_adequation * f + p.poids_intention * i + p.poids_accessibilite * a) / tot_poids)
    palier = "A" if t >= p.seuil_palier_a else "B" if t >= p.seuil_palier_b else "C"
    c.score_adequation, c.score_intention, c.score_accessibilite, c.score, c.palier = f, i, a, t, palier
    c.explication = explication(c, palier)
    if enregistrer:
        Compte.objects.filter(pk=c.pk).update(
            score=t, score_adequation=f, score_intention=i, score_accessibilite=a, palier=palier, explication=c.explication
        )
    return c


def recalculer_tout() -> int:
    p = Parametres.get()
    n = 0
    for c in Compte.objects.prefetch_related("signaux", "contacts"):
        recalculer(c, p)
        n += 1
    return n
