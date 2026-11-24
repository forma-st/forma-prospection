"""Recherche des coordonnées (adresse, standard, e-mail générique, site, dirigeants) des meilleurs prospects."""

from django.core.management.base import BaseCommand

from prospection.models import Compte
from prospection.services import coordonnees


class Command(BaseCommand):
    help = "Complète les coordonnées des prospects actifs les mieux notés (30 par défaut)."

    def add_arguments(self, parser):
        parser.add_argument("--max", type=int, default=30)
        parser.add_argument("--id", type=int, help="Un seul prospect.")

    def handle(self, *args, **opts):
        if opts.get("id"):
            c = Compte.objects.get(pk=opts["id"])
            trouve = coordonnees.enrichir(c)
            self.stdout.write(f"{c} : " + ("; ".join(trouve) if trouve else "rien de nouveau"))
            return
        b = coordonnees.enrichir_lot(opts["max"])
        self.stdout.write(f"Coordonnées : {b['examines']} prospects examinés, {b['completes']} complétés, {b['erreurs']} erreurs.")
