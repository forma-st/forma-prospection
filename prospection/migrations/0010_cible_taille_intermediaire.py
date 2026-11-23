from django.db import migrations


def cibler(apps, schema_editor):
    """Vise les entreprises de taille intermédiaire, moins disputées que les très grands groupes (voir docs/CIBLAGE.md)."""
    R = apps.get_model("prospection", "RechercheAuto")
    R.objects.filter(source__in=["sirene", "bodacc", "georisques"], effectif_max=0).update(effectif_max=2000)


class Migration(migrations.Migration):
    dependencies = [("prospection", "0009_effectif_max")]
    operations = [migrations.RunPython(cibler, migrations.RunPython.noop)]
