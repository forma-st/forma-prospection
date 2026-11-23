"""Recherche automatique de prospects (chaque nuit, avant le traitement du matin)."""

from django.core.management.base import BaseCommand

from prospection.models import RechercheAuto
from prospection.services import recherche


class Command(BaseCommand):
    help = "Exécute les recherches automatiques actives ce mois-ci."

    def add_arguments(self, parser):
        parser.add_argument("--forcer", action="store_true", help="Ignore les mois actifs.")
        parser.add_argument("--id", type=int, help="Une seule recherche.")

    def handle(self, *args, **opts):
        if opts.get("id"):
            executions = [recherche.executer(RechercheAuto.objects.get(pk=opts["id"]))]
        else:
            executions = recherche.executer_tout(forcer=opts["forcer"])
        for e in executions:
            self.stdout.write(f"{e.recherche.nom} : {e.examines} examinées, {e.crees} prospects créés, {e.signaux} signaux, {e.ignores} écartées"
                              + (f" — erreur : {e.erreur}" if e.erreur else ""))
