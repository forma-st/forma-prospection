from django.db import migrations

RECHERCHES = [
    dict(nom="Embauches à venir : logistique (La Bonne Boîte)", source="labonneboite", segment="logistique",
         mots_cles="N1101, N1103, N1105", codes_naf="", effectif_min=50, effectif_max=2000, max_par_nuit=15, mois_actifs=""),
    dict(nom="Embauches à venir : industrie (La Bonne Boîte)", source="labonneboite", segment="",
         mots_cles="H2102, H3302", codes_naf="10\n11\n20\n22\n24\n25\n28\n29", effectif_min=50, effectif_max=2000, max_par_nuit=10, mois_actifs=""),
    dict(nom="Embauches à venir : santé et médico-social (La Bonne Boîte)", source="labonneboite", segment="",
         mots_cles="J1501, J1301", codes_naf="86\n87", effectif_min=50, effectif_max=2000, max_par_nuit=10, mois_actifs=""),
]


def creer(apps, schema_editor):
    R = apps.get_model("prospection", "RechercheAuto")
    for d in RECHERCHES:
        if not R.objects.filter(nom=d["nom"]).exists():
            R.objects.create(**d)


class Migration(migrations.Migration):
    dependencies = [("prospection", "0014_la_bonne_boite")]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
