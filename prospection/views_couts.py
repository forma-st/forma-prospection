"""Écran « Coûts IA » : consommation réelle du mois, budget et simulateur."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render

from .models import AppelIA, Parametres
from .services import couts_ia
from .services.redaction import ia_disponible
from .views import _ctx


def _entier(v, defaut: int, maxi: int = 1_000_000) -> int:
    try:
        return max(0, min(maxi, int(str(v).replace(" ", ""))))
    except (TypeError, ValueError):
        return defaut


@login_required
def couts(request):
    p = Parametres.get()
    if request.method == "POST":
        if not request.user.is_staff:
            raise Http404
        p.budget_ia_mensuel = _entier(request.POST.get("budget"), p.budget_ia_mensuel, 100_000)
        p.bloquer_ia_au_budget = bool(request.POST.get("bloquer"))
        try:
            t = Decimal(request.POST.get("taux", "").replace(",", "."))
            if Decimal("0.3") <= t <= Decimal("3"):
                p.taux_usd_eur = t
        except InvalidOperation:
            pass
        p.save(update_fields=["budget_ia_mensuel", "bloquer_ia_au_budget", "taux_usd_eur"])
        messages.success(request, "Budget IA enregistré.")
        return redirect("prospection:couts_ia")

    g = request.GET
    observe = couts_ia.moyennes()
    modele = g.get("modele") if g.get("modele") in couts_ia.TARIFS else settings.CLAUDE_MODEL
    lignes = []
    for t in couts_ia.TACHES:
        k, o = t["cle"], observe.get(t["cle"])
        lignes.append({"cle": k, "libelle": t["libelle"], "aide": t["aide"], "observe": o,
                       "volume": _entier(g.get(f"v_{k}"), t["volume"]),
                       "entree": _entier(g.get(f"e_{k}"), o["entree"] if o else t["entree"]),
                       "sortie": _entier(g.get(f"s_{k}"), o["sortie"] if o else t["sortie"])})
    prospects = _entier(g.get("prospects"), 150)
    taux = float(p.taux_usd_eur)
    return render(request, "prospection/couts_ia.html", _ctx(
        request, mois=couts_ia.mois_en_cours(), sim=couts_ia.simuler(lignes, modele, taux, prospects, p.budget_ia_mensuel),
        modele=modele, modeles=[(k, v[0], v[1], v[2]) for k, v in couts_ia.TARIFS.items()], modele_actuel=settings.CLAUDE_MODEL,
        libelle_actuel=couts_ia.tarif(settings.CLAUDE_MODEL)[0], prospects=prospects, taux=taux,
        derniers=AppelIA.objects.select_related("compte")[:15], ia_dispo=ia_disponible(),
    ))
