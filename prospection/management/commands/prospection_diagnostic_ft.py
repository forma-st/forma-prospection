"""Diagnostic de la connexion France Travail : portées accordées et forme de l'API La Bonne Boîte."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from prospection.services import francetravail


class Command(BaseCommand):
    help = "Teste les identifiants France Travail et découvre l'API La Bonne Boîte (lecture seule)."

    def handle(self, *args, **opts):
        lignes = francetravail.diagnostic()
        fichier = Path(settings.BASE_DIR) / "diagnostic_francetravail.txt"
        fichier.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        for l in lignes:
            self.stdout.write(l)
        self.stdout.write(f"\nRésultat enregistré dans {fichier} (sans la clé secrète). Envoyez-le tel quel.")
