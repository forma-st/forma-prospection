"""Séquences multicanales (cahier des charges §3.7).

Une inscription avance d'étape en étape : un e-mail crée un message (à valider ou programmé selon le mode de la séquence),
une étape LinkedIn, appel ou tâche crée une tâche avec le texte prêt. Toute réponse, opposition ou RDV arrête la séquence.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .. import regles
from ..models import Activite, Compte, Contact, EtapeSequence, Inscription, Message, Sequence, Tache
from . import messagerie, qualite, redaction
from .rgpd import est_oppose
from .scoring import besoin


class InscriptionImpossible(Exception):
    pass


def _variables(c: Compte, k: Contact) -> dict:
    g = c.signal_principal()
    return {"entreprise": c.nom, "prenom": k.prenom or k.nom, "nom": k.nom, "besoin_sst": besoin(c)["sst"],
            "signal": regles.SIGNAUX[g.type]["libelle"].lower() if g else "vos obligations de formation"}


def rediger_etape(etape: EtapeSequence, k: Contact) -> tuple[str, str]:
    c = k.compte
    if etape.corps.strip():
        v = _variables(c, k)
        try:
            objet = (etape.objet or "").format(**v)
            corps = etape.corps.format(**v)
        except (KeyError, IndexError, ValueError):
            objet, corps = etape.objet, etape.corps
        from .rgpd import mention_information
        if "ne plus recevoir" not in corps:
            corps += mention_information(c.source)
        return objet or f"Formations sécurité – {c.nom}", corps
    m = redaction.generer(c, k, etape.canal_redaction or "email")
    return (etape.objet.format(**_variables(c, k)) if etape.objet else m["objet"]), m["texte"]


def inscrire(sequence: Sequence, contact: Contact, utilisateur=None) -> Inscription:
    if contact.oppose or (contact.email and est_oppose(contact.email)):
        raise InscriptionImpossible(f"{contact} est sur la liste d'opposition.")
    if contact.compte.statut in ("Opposé", "Écarté", "Client"):
        raise InscriptionImpossible(f"{contact.compte} est « {contact.compte.statut} ».")
    premiere = sequence.etapes.order_by("ordre").first()
    if not premiere:
        raise InscriptionImpossible("La séquence n'a aucune étape.")
    if premiere.type == "email" and not contact.email:
        raise InscriptionImpossible(f"{contact} n'a pas d'adresse e-mail.")
    if Inscription.objects.filter(contact=contact, statut__in=["active", "pause"]).exists():
        raise InscriptionImpossible(f"{contact} est déjà dans une séquence en cours.")
    ins = Inscription.objects.create(sequence=sequence, contact=contact, inscrit_par=utilisateur, etape_suivante=premiere.ordre,
                                     prochaine_le=timezone.now() + timedelta(days=premiere.delai_jours),
                                     boite=messagerie.boite_par_defaut(utilisateur))
    c = contact.compte
    if c.statut in ("Nouveau", "À qualifier", "À contacter"):
        c.statut = "En contact"
        c.save(update_fields=["statut"])
    Activite.objects.create(compte=c, contact=contact, type="statut", texte=f"Inscrit dans la séquence « {sequence.nom} ».", utilisateur=utilisateur)
    return ins


def arreter(contact: Contact, motif: str) -> int:
    n = 0
    for ins in Inscription.objects.filter(contact=contact, statut__in=["active", "pause"]):
        ins.statut, ins.motif_arret = "arretee", motif[:200]
        ins.save(update_fields=["statut", "motif_arret"])
        ins.messages.filter(statut__in=["a_valider", "programme"]).update(statut="annule", erreur=f"Séquence arrêtée : {motif}"[:500])
        n += 1
    return n


def mettre_en_pause(contact: Contact, jusqu_au) -> int:
    return Inscription.objects.filter(contact=contact, statut="active").update(statut="pause", prochaine_le=jusqu_au)


def avancer(maintenant=None) -> dict:
    """Exécute les étapes arrivées à échéance. Appelé toutes les 5 minutes."""
    maintenant = maintenant or timezone.now()
    res = {"emails": 0, "taches": 0, "terminees": 0}
    Inscription.objects.filter(statut="pause", prochaine_le__lte=maintenant).update(statut="active")
    for ins in Inscription.objects.filter(statut="active", prochaine_le__lte=maintenant).select_related("sequence", "contact__compte", "boite"):
        k, seq = ins.contact, ins.sequence
        etape = seq.etapes.filter(ordre=ins.etape_suivante).first()
        if not etape:
            ins.statut = "terminee"
            ins.save(update_fields=["statut"])
            res["terminees"] += 1
            continue
        if k.oppose or (k.email and est_oppose(k.email)) or k.compte.statut in ("Opposé", "Écarté", "RDV fixé", "Client"):
            ins.statut, ins.motif_arret = "arretee", "Prospect opposé, écarté, client ou RDV fixé"
            ins.save(update_fields=["statut", "motif_arret"])
            continue
        if etape.type == "email":
            objet, corps = rediger_etape(etape, k)
            corps = messagerie.appliquer_signature(corps, ins.boite)
            note = (qualite.controler(corps, "email", k.compte) or {}).get("note")
            premier = not ins.messages.filter(sens="sortant").exclude(statut="annule").exists()
            a_valider = seq.mode_validation == "brouillon" or (seq.mode_validation == "premier" and premier) or (note is not None and note < 60)
            precedent = ins.messages.filter(sens="sortant", statut="envoye").order_by("-envoye_le").first()
            m = Message.objects.create(compte=k.compte, contact=k, boite=ins.boite, inscription=ins, destinataire=k.email, objet=objet,
                                       corps=corps, note_qualite=note, statut="a_valider" if a_valider else "programme",
                                       prevu_le=None if a_valider else messagerie.prochain_creneau(maintenant),
                                       en_reponse_a=precedent.message_id if precedent and etape.canal_redaction == "relance" else "")
            res["emails"] += 1
        else:
            canal = {"linkedin": "linkedin", "appel": "appel"}.get(etape.type, "")
            titre = etape.intitule or {"linkedin": f"LinkedIn : contacter {k}", "appel": f"Appeler {k}"}.get(etape.type, f"Suivi de {k}")
            Tache.objects.create(compte=k.compte, contact=k, type={"linkedin": "linkedin", "appel": "appel"}.get(etape.type, "autre"),
                                 titre=f"{titre} ({seq.nom})", echeance=timezone.localdate(), assignee=ins.inscrit_par, origine=f"Séquence {seq.nom}")
            res["taches"] += 1
        suivante = seq.etapes.filter(ordre__gt=etape.ordre).order_by("ordre").first()
        if suivante:
            ins.etape_suivante, ins.prochaine_le = suivante.ordre, maintenant + timedelta(days=suivante.delai_jours)
        else:
            ins.etape_suivante, ins.statut = etape.ordre + 1, "terminee"
            res["terminees"] += 1
        ins.save(update_fields=["etape_suivante", "prochaine_le", "statut"])
    return res
