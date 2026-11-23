"""À lancer toutes les 5 minutes : avance les séquences, envoie la file d'attente, relève les réponses."""

from django.core.management.base import BaseCommand

from prospection.services import messagerie, reponses, sequences


class Command(BaseCommand):
    help = "Séquences, envois programmés et relève des réponses."

    def add_arguments(self, parser):
        parser.add_argument("--sans-releve", action="store_true")

    def handle(self, *args, **opts):
        s = sequences.avancer()
        f = messagerie.traiter_file()
        r = {"reponses": 0, "erreurs": []} if opts["sans_releve"] else reponses.relever_tout()
        self.stdout.write(
            f"Séquences : {s['emails']} e-mails préparés, {s['taches']} tâches, {s['terminees']} terminées. "
            f"Envois : {f['envoyes']} partis, {f['erreurs']} refusés{' (hors plage horaire)' if f['hors_plage'] else ''}. "
            f"Réponses : {r['reponses']} relevées." + (" Erreurs de relève : " + " ; ".join(r["erreurs"]) if r["erreurs"] else "")
        )
