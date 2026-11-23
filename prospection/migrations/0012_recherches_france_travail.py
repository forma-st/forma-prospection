from django.db import migrations

RECHERCHES = [
    dict(nom="Recrutements QSE / HSE (France Travail)", source="francetravail", segment="",
         mots_cles="QSE, HSE, responsable sécurité, animateur sécurité, préventeur, responsable prévention",
         codes_naf="", effectif_min=50, effectif_max=2000, max_par_nuit=15, mois_actifs=""),
    dict(nom="Recrutements en nombre : logistique, industrie, commerce, santé (France Travail)", source="francetravail", segment="",
         mots_cles="", seuil_offres=10, codes_naf="10\n11\n20\n22\n24\n25\n47\n49\n52\n86\n87",
         effectif_min=50, effectif_max=2000, max_par_nuit=10, mois_actifs="1,2,3,4,8,9,10"),
]


def creer(apps, schema_editor):
    R = apps.get_model("prospection", "RechercheAuto")
    for d in RECHERCHES:
        if not R.objects.filter(source="francetravail").filter(nom=d["nom"]).exists():
            R.objects.create(**d)


class Migration(migrations.Migration):
    dependencies = [("prospection", "0011_france_travail")]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
