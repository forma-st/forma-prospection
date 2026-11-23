from django.db import migrations

# Recherches par défaut : France entière, sites industriels et réseaux multi-sites (voir docs/CIBLAGE.md)
RECHERCHES = [
    dict(nom="Logistique et entreposage (50 salariés et plus)", source="sirene", segment="logistique", effectif_min=50, etablissements_min=1,
         codes_naf="52.10A\n52.10B\n52.29A\n52.29B\n49.41A\n49.41B\n53.20Z", mois_actifs="", max_par_nuit=15),
    dict(nom="Industrie agroalimentaire (50 salariés et plus)", source="sirene", segment="industrie", effectif_min=50, etablissements_min=1,
         codes_naf="10\n11", mois_actifs="", max_par_nuit=10),
    dict(nom="Industrie chimie, plasturgie, métallurgie (50 salariés et plus)", source="sirene", segment="industrie", effectif_min=50, etablissements_min=1,
         codes_naf="20\n22\n24\n25", mois_actifs="", max_par_nuit=10),
    dict(nom="Réseaux de magasins et d'agences (10 sites et plus)", source="sirene", segment="commerce", effectif_min=100, etablissements_min=10,
         codes_naf="47\n77\n78", mois_actifs="1,2,3,9,10,11", max_par_nuit=10),
    dict(nom="Santé et médico-social : groupes (3 sites et plus)", source="sirene", segment="sante", effectif_min=100, etablissements_min=3,
         codes_naf="86.10Z\n87.10A\n87.10B\n87.30A", mois_actifs="", max_par_nuit=8),
    dict(nom="Hôtellerie-restauration en réseau (5 sites et plus)", source="sirene", segment="hotellerie", effectif_min=50, etablissements_min=5,
         codes_naf="55.10Z\n56.10A\n56.10C\n56.21Z", mois_actifs="2,3,4,5", max_par_nuit=8),
    dict(nom="Sites industriels classés (ICPE)", source="georisques", segment="", effectif_min=50, etablissements_min=1,
         codes_naf="", mois_actifs="", max_par_nuit=10),
    dict(nom="Nouveaux établissements (BODACC)", source="bodacc", segment="", effectif_min=50, etablissements_min=1,
         codes_naf="10\n11\n20\n22\n24\n25\n47\n49\n52\n86\n87", mois_actifs="", max_par_nuit=10),
]


def creer(apps, schema_editor):
    R = apps.get_model("prospection", "RechercheAuto")
    if not R.objects.exists():
        for d in RECHERCHES:
            R.objects.create(**d)


class Migration(migrations.Migration):
    dependencies = [("prospection", "0006_recherche_auto")]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
