"""Charge des données FICTIVES pour découvrir l'outil (domaines .example). --effacer les retire."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from prospection.models import Compte, Contact, HistoriqueFormation, Signal, Tache
from prospection.services.scoring import recalculer

SOURCE = "Démonstration (fictif)"
DEMO = [
    ("Logistique du Vexin (démo)", "Cergy", "95000", "logistique", "52.10B", 240, 2, True, False,
     [("qse", 6, "Offre d'emploi « Responsable HSE (CDI) » publiée", "France Travail"), ("site", 25, "Nouvel établissement immatriculé à Saint-Ouen-l'Aumône", "BODACC")],
     [("Claire", "Vasseur", "Directrice des ressources humaines", "decideur", "c.vasseur@logistique-vexin.example", "verifie", ""), ("", "Standard", "Accueil", "standard", "contact@logistique-vexin.example", "verifie", "01 30 00 00 01")]),
    ("Clinique des Hauts-Prés (démo)", "Eaubonne", "95600", "sante", "86.10Z", 310, 1, False, True,
     [("dirigeant", 40, "Nomination d'une nouvelle directrice des soins", "Presse locale")],
     [("Sophie", "Lemaire", "Directrice des ressources humaines", "decideur", "s.lemaire@cliniquehp.example", "probable", "")]),
    ("Métallerie Durand & Fils (démo)", "Beauvais", "60000", "industrie", "25.11Z", 95, 1, True, False,
     [("recrut", 9, "14 offres d'emploi ouvertes (soudeurs, opérateurs)", "France Travail")],
     [("Pascal", "Durand", "Gérant", "decideur", "", "absent", "03 44 00 00 04")]),
    ("Syndicat Val-Nord Services (démo)", "Sarcelles", "95200", "collectivite", "84.11Z", 420, 12, False, True,
     [("marche", 120, "Marché de formation sécurité attribué en 2023 pour 3 ans : échéance estimée mars 2027", "DECP")],
     [("Nadia", "Benali", "Responsable formation", "decideur", "n.benali@valnord.example", "verifie", "")]),
    ("Transports Lefèvre Express (démo)", "Gonesse", "95500", "logistique", "49.41A", 130, 3, False, False, [], []),
]


class Command(BaseCommand):
    help = "Charge (ou retire avec --effacer) des prospects fictifs de démonstration."

    def add_arguments(self, parser):
        parser.add_argument("--effacer", action="store_true")

    def handle(self, *args, **opts):
        if opts["effacer"]:
            n = Compte.objects.filter(source=SOURCE).count()
            Compte.objects.filter(source=SOURCE).delete()
            HistoriqueFormation.objects.filter(source="demo").delete()
            self.stdout.write(f"{n} prospects de démonstration supprimés.")
            return
        today = timezone.localdate()
        for nom, ville, cp, seg, naf, eff, sites, icpe, erp, sigs, contacts in DEMO:
            c, cree = Compte.objects.get_or_create(nom=nom, defaults=dict(ville=ville, code_postal=cp, segment=seg, naf=naf, effectif=eff,
                                                   nb_etablissements=sites, icpe=icpe, erp=erp, source=SOURCE, statut="À contacter"))
            if cree:
                for t, age, txt, src in sigs:
                    Signal.objects.create(compte=c, type=t, texte=txt, source=src, date_signal=today - timedelta(days=age))
                for pr, nm, f, role, email, es, tel in contacts:
                    Contact.objects.create(compte=c, prenom=pr, nom=nm, fonction=f, role=role, email=email, statut_email=es, telephone=tel)
            recalculer(c)
        client, _ = Compte.objects.get_or_create(nom="Boulangeries Marceau (démo)", defaults=dict(ville="Versailles", code_postal="78000", segment="commerce",
                                                 naf="10.71C", effectif=190, nb_etablissements=22, erp=True, est_client=True, statut="Client", source=SOURCE))
        recalculer(client)
        HistoriqueFormation.objects.get_or_create(nom_client=client.nom, prestation="MAC SST", defaults=dict(compte=client, date_session=today - timedelta(days=730 - 60), nb_stagiaires=12, source="demo"))
        Tache.objects.get_or_create(titre="Appeler Claire Vasseur (DRH) – démo", defaults=dict(compte=Compte.objects.get(nom=DEMO[0][0]), type="appel", echeance=today))
        self.stdout.write("Données de démonstration chargées (fictives).")
