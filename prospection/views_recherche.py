"""Écran de la recherche automatique de prospects."""

from __future__ import annotations

import threading

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import close_old_connections
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import regles
from .models import ExecutionRecherche, RechercheAuto
from .services import recherche as svc
from .views import _ctx

CHAMPS = ["nom", "source", "codes_naf", "departements", "segment", "palier_min", "mois_actifs"]
NOMBRES = ["effectif_min", "effectif_max", "etablissements_min", "max_par_nuit"]


def _lancer_en_arriere_plan(r: RechercheAuto) -> None:
    def cible():
        close_old_connections()
        try:
            svc.executer(r)
        finally:
            close_old_connections()
    threading.Thread(target=cible, daemon=True).start()


@login_required
def recherches(request):
    if request.method == "POST":
        if not request.user.is_staff:
            raise Http404
        a = request.POST.get("action")
        if a == "lancer":
            r = get_object_or_404(RechercheAuto, pk=request.POST.get("id"))
            _lancer_en_arriere_plan(r)
            messages.success(request, f"Recherche « {r.nom} » lancée. Les résultats apparaissent dans le journal ci-dessous d'ici quelques minutes.")
        elif a == "basculer":
            r = get_object_or_404(RechercheAuto, pk=request.POST.get("id"))
            r.actif = not r.actif
            r.save(update_fields=["actif"])
        elif a == "enregistrer":
            r = RechercheAuto.objects.filter(pk=request.POST.get("id")).first() or RechercheAuto()
            for champ in CHAMPS:
                if champ in request.POST:
                    setattr(r, champ, request.POST[champ].strip())
            for champ in NOMBRES:
                v = request.POST.get(champ, "")
                if v.isdigit():
                    setattr(r, champ, int(v))
            if not r.nom:
                messages.error(request, "Donnez un nom à la recherche.")
            else:
                r.save()
                messages.success(request, f"Recherche « {r.nom} » enregistrée.")
                return redirect(f"{request.path}?id={r.pk}")
        return redirect(request.get_full_path())
    liste = RechercheAuto.objects.prefetch_related("executions")
    mois = timezone.localdate().month
    return render(request, "prospection/recherches.html", _ctx(
        request, liste=liste, edit=RechercheAuto.objects.filter(pk=request.GET.get("id")).first() if request.GET.get("id") else None,
        nouveau=request.GET.get("nouveau"), journal=ExecutionRecherche.objects.select_related("recherche")[:30], sources=RechercheAuto.SOURCES,
        segments=regles.SEGMENT_CHOICES, saison=regles.SAISONS[mois], mois=mois, bilan=svc.bilan_nuit(),
    ))
