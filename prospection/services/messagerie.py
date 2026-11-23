"""Envoi des e-mails (cahier des charges §3.16).

- File d'attente : un message « programmé » part à son heure, dans les plages d'envoi (jours ouvrés), sous le plafond de sa boîte.
- Envoi jamais doublé : le message passe en « envoi en cours » par une mise à jour atomique avant la connexion SMTP.
- Mode test (Paramètres, activé par défaut) : tout part vers l'adresse de test, l'objet indique le vrai destinataire.
- Opposition vérifiée au dernier moment ; mention RGPD et en-têtes de désinscription toujours présents.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import datetime, time, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from django.db import transaction
from django.utils import timezone

from ..models import Activite, BoiteEnvoi, Message, Parametres
from .rgpd import est_oppose

log = logging.getLogger("prospection.messagerie")


class EnvoiImpossible(Exception):
    pass


def plages(p: Parametres | None = None) -> list[tuple[time, time]]:
    p = p or Parametres.get()
    res = []
    for bloc in (p.plages_envoi or "").split(","):
        try:
            a, b = bloc.strip().split("-")
            res.append((time.fromisoformat(a.strip()), time.fromisoformat(b.strip())))
        except ValueError:
            continue
    return res or [(time(8, 30), time(11, 30)), (time(14, 0), time(17, 0))]


def dans_les_plages(moment: datetime, p: Parametres | None = None) -> bool:
    m = timezone.localtime(moment)
    return m.weekday() < 5 and any(a <= m.time() <= b for a, b in plages(p))


def prochain_creneau(moment: datetime, p: Parametres | None = None) -> datetime:
    """Premier instant autorisé à partir de « moment »."""
    m = timezone.localtime(moment)
    pl = sorted(plages(p))
    for _ in range(10):
        if m.weekday() < 5:
            for a, b in pl:
                if m.time() <= b:
                    debut = m if m.time() >= a else m.replace(hour=a.hour, minute=a.minute, second=0, microsecond=0)
                    return debut
        m = (m + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return m


def appliquer_signature(texte: str, boite: BoiteEnvoi | None) -> str:
    if boite and boite.signature:
        bloc = "[Prénom Nom]\nFORMA'ST – Formation santé et sécurité au travail\n[Téléphone]"
        if bloc in texte:
            return texte.replace(bloc, boite.signature.strip())
        return texte.replace("[Prénom Nom]", boite.signature.strip()).replace("\n[Téléphone]", "")
    return texte


def boite_par_defaut(utilisateur=None) -> BoiteEnvoi | None:
    qs = BoiteEnvoi.objects.filter(actif=True)
    return (qs.filter(utilisateur=utilisateur).first() if utilisateur else None) or qs.first()


def _construire(m: Message, p: Parametres) -> tuple[EmailMessage, str]:
    b = m.boite
    vers = m.destinataire
    objet = m.objet
    if p.mode_test:
        if not p.adresse_test:
            raise EnvoiImpossible("Mode test activé sans adresse de test : renseignez-la dans Paramètres.")
        vers, objet = p.adresse_test, f"[TEST → {m.destinataire}] {m.objet}"
    e = EmailMessage()
    e["From"] = formataddr((b.nom_affiche or b.nom, b.adresse))
    e["To"] = vers
    e["Subject"] = objet
    e["Message-ID"] = m.message_id or make_msgid(domain=b.adresse.split("@")[-1])
    e["List-Unsubscribe"] = f"<mailto:{b.adresse}?subject=STOP>"
    if m.en_reponse_a:
        e["In-Reply-To"] = m.en_reponse_a
        e["References"] = m.en_reponse_a
    e.set_content(m.corps)
    return e, vers


def _smtp(b: BoiteEnvoi):
    contexte = ssl.create_default_context()
    if b.smtp_securite == "ssl":
        s = smtplib.SMTP_SSL(b.smtp_hote, b.smtp_port, timeout=30, context=contexte)
    else:
        s = smtplib.SMTP(b.smtp_hote, b.smtp_port, timeout=30)
        if b.smtp_securite == "starttls":
            s.starttls(context=contexte)
    if b.smtp_identifiant:
        s.login(b.smtp_identifiant, b.smtp_mot_de_passe)
    return s


def tester_boite(b: BoiteEnvoi) -> str:
    """Connexion SMTP (et IMAP si renseigné) sans rien envoyer. Renvoie un compte rendu lisible."""
    try:
        with _smtp(b):
            pass
        res = "Envoi (SMTP) : connexion réussie."
    except Exception as e:
        res = f"Envoi (SMTP) : échec – {e}"
    if b.imap_hote:
        import imaplib
        try:
            with imaplib.IMAP4_SSL(b.imap_hote, b.imap_port, timeout=30) as i:
                i.login(b.imap_identifiant or b.adresse, b.imap_mot_de_passe)
            res += " Réponses (IMAP) : connexion réussie."
        except Exception as e:
            res += f" Réponses (IMAP) : échec – {e}"
    return res


def envoyer(m: Message, p: Parametres | None = None, connexion=None) -> Message:
    """Envoie un message (déjà validé). Lève EnvoiImpossible avec une explication."""
    p = p or Parametres.get()
    if not m.boite or not m.boite.actif:
        raise EnvoiImpossible("Aucune boîte d'envoi active : ajoutez-en une dans Messagerie.")
    if est_oppose(m.destinataire) or (m.contact and m.contact.oppose):
        Message.objects.filter(pk=m.pk).update(statut="annule", erreur="Destinataire sur la liste d'opposition.")
        raise EnvoiImpossible("Destinataire sur la liste d'opposition : envoi annulé.")
    if m.boite.envoyes_aujourd_hui() >= m.boite.plafond_jour:
        raise EnvoiImpossible(f"Plafond du jour atteint pour {m.boite.adresse} ({m.boite.plafond_jour}).")
    # verrou : un seul envoi possible, même si deux traitements tournent en même temps
    with transaction.atomic():
        pris = Message.objects.filter(pk=m.pk, statut__in=["programme", "erreur"]).update(statut="envoi")
    if not pris:
        raise EnvoiImpossible("Ce message est déjà en cours d'envoi ou envoyé.")
    m.refresh_from_db()
    try:
        e, vers = _construire(m, p)
        if connexion is not None:
            connexion.send_message(e)
        else:
            with _smtp(m.boite) as s:
                s.send_message(e)
    except Exception as ex:
        Message.objects.filter(pk=m.pk).update(statut="erreur", erreur=str(ex)[:1000])
        BoiteEnvoi.objects.filter(pk=m.boite_id).update(derniere_erreur=str(ex)[:500])
        raise EnvoiImpossible(f"Envoi refusé par le serveur : {ex}") from ex
    m.statut, m.envoye_le, m.message_id, m.redirige_test, m.erreur = "envoye", timezone.now(), e["Message-ID"], p.mode_test, ""
    m.save(update_fields=["statut", "envoye_le", "message_id", "redirige_test", "erreur"])
    if m.compte_id:
        Activite.objects.create(compte_id=m.compte_id, contact=m.contact, type="email",
                                texte=f"E-mail envoyé{' (mode test)' if p.mode_test else ''} : {m.objet}")
    if m.contact and not m.contact.informe_le and not p.mode_test:
        m.contact.informe_le = timezone.now()
        m.contact.save(update_fields=["informe_le"])
    return m


def traiter_file(maintenant: datetime | None = None, connexion=None) -> dict:
    """Envoie les messages programmés dont l'heure est passée, si l'on est dans une plage d'envoi."""
    p = Parametres.get()
    maintenant = maintenant or timezone.now()
    res = {"envoyes": 0, "erreurs": 0, "hors_plage": not dans_les_plages(maintenant, p)}
    if res["hors_plage"]:
        return res
    for m in Message.objects.filter(sens="sortant", statut="programme", prevu_le__lte=maintenant).select_related("boite", "contact")[:200]:
        try:
            envoyer(m, p, connexion)
            res["envoyes"] += 1
        except EnvoiImpossible as e:
            log.info("Message %s non envoyé : %s", m.pk, e)
            res["erreurs"] += 1
    return res


def programmer(m: Message, valide_par=None, quand: datetime | None = None) -> Message:
    """Valide un message et le place dans la file, au prochain créneau autorisé."""
    m.statut = "programme"
    m.valide_par = valide_par or m.valide_par
    m.prevu_le = prochain_creneau(quand or timezone.now())
    m.save(update_fields=["statut", "valide_par", "prevu_le", "objet", "corps"])
    return m
