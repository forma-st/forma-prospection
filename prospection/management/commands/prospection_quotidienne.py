"""Traitement quotidien de la prospection (à planifier chaque matin).

- reprise des prospects « Pas maintenant » arrivés à leur date ;
- relances des formations arrivées à échéance (tâches + signal MAC SST) ;
- recalcul de tous les scores (les signaux perdent de la valeur avec le temps) ;
- option --sirene : rapprochement avec l'annuaire des fiches jamais rapprochées (50 max par jour).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from prospection.models import Activite, Compte, HistoriqueFormation, Tache
from prospection.services import sirene
from prospection.services.scoring import recalculer_tout


class Command(BaseCommand):
    help = "Reprises, relances d'échéances, recalcul des scores (et rapprochement annuaire avec --sirene)."

    def add_arguments(self, parser):
        parser.add_argument("--sirene", action="store_true", help="Rapprocher les fiches sans SIREN (50 max).")

    def handle(self, *args, **opts):
        from prospection.views import creer_relance

        aujourd_hui = timezone.localdate()
        reprises = 0
        for c in Compte.objects.filter(statut="Pas maintenant", date_reprise__lte=aujourd_hui):
            c.statut, c.date_reprise = "À contacter", None
            c.save(update_fields=["statut", "date_reprise"])
            Tache.objects.create(compte=c, type="appel", titre=f"Reprendre contact avec {c.nom} (date de reprise)", echeance=aujourd_hui, origine="Reprise")
            Activite.objects.create(compte=c, type="statut", texte="Date de reprise atteinte : retour en « À contacter ».")
            reprises += 1
        relances = 0
        for h in HistoriqueFormation.objects.filter(relance_creee=False):
            if h.etat != "ok":
                creer_relance(h)
                relances += 1
        rapproches = 0
        if opts["sirene"]:
            for c in Compte.objects.filter(siren="", sirene_le__isnull=True).exclude(statut__in=["Écarté", "Opposé"])[:50]:
                ok, _ = sirene.rapprocher(c)
                rapproches += ok
        n = recalculer_tout()
        self.stdout.write(f"{reprises} reprises, {relances} relances, {rapproches} fiches rapprochées, {n} scores recalculés.")
