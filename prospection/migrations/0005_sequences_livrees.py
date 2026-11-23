from django.db import migrations

# Délais : jours après l'étape précédente (J0, J+2, J+5, J+9, J+16 pour « Ouverture de site »)
SEQUENCES = [
    ("Ouverture de site", "Nouvel établissement : former les équipes avant l'ouverture", "premier", [
        ("email", 0, "email", ""), ("linkedin", 2, "", "Inviter le décideur sur LinkedIn"), ("appel", 3, "", "Appel de découverte"),
        ("email", 4, "relance", ""), ("email", 7, "relance", "")]),
    ("Recrutement QSE", "Offre d'emploi QSE / HSE : épauler la prévention", "premier", [
        ("email", 0, "email", ""), ("linkedin", 1, "", "Inviter le DRH sur LinkedIn"), ("email", 6, "relance", ""), ("appel", 6, "", "Appeler le DRH")]),
    ("Réactivation MAC SST", "Clients : recyclage SST à échéance", "premier", [
        ("email", 0, "email", ""), ("appel", 7, "", "Appel de confirmation des dates"), ("email", 14, "relance", "")]),
    ("Acheteur public avant marché", "Rendez-vous de sourçage avant la publication", "brouillon", [
        ("email", 0, "email", ""), ("appel", 10, "", "Appeler le service formation"), ("email", 10, "relance", "")]),
]


def creer(apps, schema_editor):
    Sequence = apps.get_model("prospection", "Sequence")
    Etape = apps.get_model("prospection", "EtapeSequence")
    if Sequence.objects.exists():
        return
    for nom, desc, mode, etapes in SEQUENCES:
        s = Sequence.objects.create(nom=nom, description=desc, mode_validation=mode)
        for i, (type_, delai, canal, intitule) in enumerate(etapes, start=1):
            Etape.objects.create(sequence=s, ordre=i, type=type_, delai_jours=delai, canal_redaction=canal or "email", intitule=intitule)


class Migration(migrations.Migration):
    dependencies = [("prospection", "0004_messagerie_sequences")]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
