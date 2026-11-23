"""Relève et tri des réponses (cahier des charges §3.8).

Relève IMAP des boîtes, rattachement au message d'origine (In-Reply-To / References, sinon adresse de l'expéditeur),
classement par règles (et par l'IA si une clé est présente), puis actions automatiques sans risque :
séquence arrêtée, opposition appliquée, pause en cas d'absence. Le reste est proposé dans « Réponses ».
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
from datetime import date, datetime, time, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr

from django.utils import timezone

from ..models import Activite, BoiteEnvoi, Contact, Message, Tache
from . import sequences
from .rgpd import enregistrer_opposition

log = logging.getLogger("prospection.reponses")

REGLES = [
    ("opposition", 99, r"\b(stop|d[ée]sinscri|ne plus (m'|me )?(écrire|ecrire|contacter|recevoir)|retirez[- ]moi|unsubscribe|plus de (mails?|messages?))\b"),
    ("rebond", 99, r"(delivery status notification|undeliverable|non distribu|mail delivery (failed|subsystem)|adresse (introuvable|inconnue))"),
    ("absence", 95, r"(absent|en cong[ée]s|out of office|r[ée]ponse automatique|je serai de retour|automatic reply)"),
    ("mauvais_interlocuteur", 85, r"(voyez avec|adressez[- ]vous|contactez plut[ôo]t|je transmets|n'est pas (moi|mon domaine)|ce n'est pas moi|g[ée]r[ée] par)"),
    ("deja_equipe", 85, r"(d[ée]j[àa] (un|une|avec un) (prestataire|organisme)|travaillons d[ée]j[àa]|nous avons d[ée]j[àa]|en interne)"),
    ("pas_maintenant", 85, r"(pas (pour le moment|maintenant|en ce moment|cette ann[ée]e)|revenez|recontactez|plus tard|l'an prochain|au (prochain|premier) trimestre|en (janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre))"),
    ("interesse", 85, r"(int[ée]ress|appelez[- ]moi|rappelez[- ]moi|rendez[- ]vous|disponible|volontiers|envoyez[- ]moi|devis|proposition|quand pouvons|cr[ée]neau)"),
]
MOIS = {"janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12}


def classer(texte: str, objet: str = "", auto_reply: bool = False) -> tuple[str, int]:
    t = f"{objet}\n{texte}".lower()
    t = t.split("\n>")[0]  # ignore la citation du message d'origine
    if auto_reply:
        return "absence", 95
    for classe, conf, motif in REGLES:
        if re.search(motif, t):
            return classe, conf
    return "autre", 40


def date_reprise(texte: str, aujourd_hui: date | None = None) -> date | None:
    aujourd_hui = aujourd_hui or timezone.localdate()
    t = texte.lower()
    m = re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", t)
    if m:
        j, mo = int(m.group(1)), int(m.group(2))
        a = int(m.group(3)) if m.group(3) else aujourd_hui.year
        a = a + 2000 if a < 100 else a
        try:
            d = date(a, mo, j)
            return d if d >= aujourd_hui else date(a + 1, mo, j)
        except ValueError:
            pass
    for nom, num in MOIS.items():
        if re.search(rf"\b{nom}\b", t):
            a = aujourd_hui.year if num > aujourd_hui.month else aujourd_hui.year + 1
            return date(a, num, 1)
    if "l'an prochain" in t or "l'année prochaine" in t:
        return date(aujourd_hui.year + 1, 1, 15)
    return None


def _texte(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                return re.sub(r"<[^>]+>", " ", html)
        return ""
    return (msg.get_payload(decode=True) or b"").decode(msg.get_content_charset() or "utf-8", "replace")


def enregistrer(boite: BoiteEnvoi, brut: bytes) -> Message | None:
    msg = email.message_from_bytes(brut)
    exp = parseaddr(msg.get("From", ""))[1].lower()
    if not exp or exp == boite.adresse.lower():
        return None
    objet = str(make_header(decode_header(msg.get("Subject", ""))))[:255]
    refs = " ".join(filter(None, [msg.get("In-Reply-To", ""), msg.get("References", "")]))
    ids = re.findall(r"<[^>]+>", refs)
    origine = Message.objects.filter(sens="sortant", message_id__in=ids).select_related("contact", "compte").first() if ids else None
    contact = origine.contact if origine else Contact.objects.filter(email__iexact=exp).select_related("compte").first()
    if not origine and not contact:
        return None  # e-mail sans rapport avec la prospection
    msg_id = msg.get("Message-ID", "")
    if msg_id and Message.objects.filter(message_id=msg_id).exists():
        return None
    corps = _texte(msg)
    auto = (msg.get("Auto-Submitted", "no").lower() != "no") or bool(msg.get("X-Autoreply")) or "auto-reply" in msg.get("X-Auto-Response-Suppress", "").lower()
    classe, conf = classer(corps, objet, auto)
    if "mailer-daemon" in exp or "postmaster" in exp:
        classe, conf = "rebond", 99
    compte = origine.compte if origine else contact.compte
    r = Message.objects.create(compte=compte, contact=contact, boite=boite, sens="entrant", expediteur=exp, objet=objet or "(sans objet)",
                               corps=corps[:20000], statut="recu", message_id=msg_id, en_reponse_a=origine.message_id if origine else "",
                               classe=classe, confiance=conf, date_reprise=date_reprise(corps) if classe == "pas_maintenant" else None)
    appliquer(r)
    return r


def appliquer(r: Message) -> None:
    """Actions automatiques sans risque. Le reste attend une décision dans « Réponses »."""
    k, c = r.contact, r.compte
    if not k:
        return
    if r.classe == "absence":
        retour = date_reprise(r.corps) or (timezone.localdate() + timedelta(days=7))
        sequences.mettre_en_pause(k, timezone.make_aware(datetime.combine(retour, time(8, 30))))
        r.traite = True
    elif r.classe == "opposition":
        sequences.arreter(k, "Demande d'opposition")
        if r.expediteur:
            enregistrer_opposition(r.expediteur, source="Réponse e-mail")
        k.oppose = True
        k.save(update_fields=["oppose"])
        r.traite = True
    elif r.classe == "rebond":
        sequences.arreter(k, "Adresse invalide")
        k.statut_email = "invalide"
        k.save(update_fields=["statut_email"])
        r.traite = True
    else:
        sequences.arreter(k, f"Réponse reçue ({r.get_classe_display().lower()})")
        if c and c.statut in ("Nouveau", "À qualifier", "À contacter", "En contact"):
            c.statut = "A répondu"
            c.save(update_fields=["statut"])
        k.dernier_contact_entrant_le = timezone.now()
        k.save(update_fields=["dernier_contact_entrant_le"])
        if r.classe == "interesse":
            Tache.objects.create(compte=c, contact=k, type="appel", titre=f"Rappeler {k} : réponse intéressée", echeance=timezone.localdate(),
                                 origine="Réponse e-mail")
    r.save(update_fields=["traite"])
    if c:
        Activite.objects.create(compte=c, contact=k, type="email", texte=f"Réponse reçue ({r.get_classe_display()}, {r.confiance} %) : {r.objet}")


def relever(boite: BoiteEnvoi, limite: int = 200) -> int:
    if not boite.imap_hote:
        return 0
    n = 0
    with imaplib.IMAP4_SSL(boite.imap_hote, boite.imap_port, timeout=60) as i:
        i.login(boite.imap_identifiant or boite.adresse, boite.imap_mot_de_passe)
        i.select("INBOX", readonly=True)
        typ, data = i.uid("search", None, f"UID {boite.imap_dernier_uid + 1}:*")
        uids = [int(u) for u in (data[0] or b"").split() if int(u) > boite.imap_dernier_uid][:limite]
        for uid in uids:
            typ, d = i.uid("fetch", str(uid), "(BODY.PEEK[])")
            if d and d[0] and isinstance(d[0], tuple):
                try:
                    if enregistrer(boite, d[0][1]):
                        n += 1
                except Exception as e:  # un e-mail illisible ne bloque pas la relève
                    log.warning("Réponse %s illisible : %s", uid, e)
            boite.imap_dernier_uid = uid
        boite.save(update_fields=["imap_dernier_uid"])
    return n


def relever_tout() -> dict:
    res = {"reponses": 0, "erreurs": []}
    for b in BoiteEnvoi.objects.filter(actif=True).exclude(imap_hote=""):
        try:
            res["reponses"] += relever(b)
        except Exception as e:
            res["erreurs"].append(f"{b.adresse} : {e}")
            BoiteEnvoi.objects.filter(pk=b.pk).update(derniere_erreur=f"Relève : {e}"[:500])
    return res
