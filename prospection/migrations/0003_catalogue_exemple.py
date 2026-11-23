from django.db import migrations

EXEMPLES = [
    ("SST initial (2 j, 4 à 10 personnes)", "sst", "2j", 1450),
    ("MAC SST (1 j)", "mac", "1j", 820),
    ("Gestes et postures (1 j)", "gp", "1j", 980),
    ("Exercice d'évacuation / manipulation des extincteurs (½ j)", "incendie", "3h30", 690),
]


def creer(apps, schema_editor):
    Prestation = apps.get_model("prospection", "Prestation")
    ProfilEntreprise = apps.get_model("prospection", "ProfilEntreprise")
    if not Prestation.objects.exists():
        for intitule, usage, duree, prix in EXEMPLES:
            Prestation.objects.create(intitule=intitule, usage_potentiel=usage, duree=duree, prix_intra_ht=prix, exemple=True)
    ProfilEntreprise.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("prospection", "0002_prestation_profilentreprise")]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
