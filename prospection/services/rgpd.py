"""Opposition globale et contrôles RGPD (cahier des charges §3.13)."""

from __future__ import annotations

from ..models import Activite, Compte, Contact, Opposition


def est_oppose(email: str) -> bool:
    e = (email or "").strip().lower()
    if not e:
        return False
    domaine = "@" + e.split("@", 1)[1] if "@" in e else ""
    return Opposition.objects.filter(valeur__in=[e, domaine] if domaine else [e]).exists()


def enregistrer_opposition(valeur: str, source: str = "", utilisateur=None) -> int:
    """Ajoute l'adresse ou le domaine à la liste et bloque les contacts concernés. Renvoie le nombre bloqué."""
    v = valeur.strip().lower()
    Opposition.objects.get_or_create(valeur=v, defaults={"source": source})
    qs = Contact.objects.filter(email__iendswith=v) if v.startswith("@") else Contact.objects.filter(email__iexact=v)
    n = 0
    for c in qs.filter(oppose=False):
        c.oppose = True
        c.save(update_fields=["oppose"])
        Activite.objects.create(compte=c.compte, contact=c, type="systeme", texte=f"Opposition enregistrée ({v}) : plus aucun envoi.", utilisateur=utilisateur)
        n += 1
    return n


def opposer_compte(compte: Compte, utilisateur=None) -> None:
    for c in compte.contacts.all():
        if c.email:
            enregistrer_opposition(c.email, source=f"Fiche {compte.nom}", utilisateur=utilisateur)
        c.oppose = True
        c.save(update_fields=["oppose"])
    compte.statut = "Opposé"
    compte.save(update_fields=["statut"])
    Activite.objects.create(compte=compte, type="statut", texte="Opposition : prospect exclu de tout envoi, sur tous les canaux.", utilisateur=utilisateur)


def mention_information(source: str) -> str:
    return (
        "\n\n—\n"
        f"Vos coordonnées professionnelles proviennent de : {source or 'nos recherches'}. "
        "FORMA'ST les utilise pour vous présenter ses formations en santé et sécurité au travail, pendant 3 ans au plus "
        "après notre dernier échange.\n"
        "Pour ne plus recevoir nos messages, répondez simplement « STOP » à cet e-mail."
    )
