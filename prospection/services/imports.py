"""Import de bases fournies et de l'historique des formations (cahier des charges §3.1.2 et §3.17)."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from .. import regles
from ..models import Activite, Compte, Contact, HistoriqueFormation, ImportFichier
from .rgpd import est_oppose
from .scoring import recalculer

CHAMPS_PROSPECTS = {
    "": "— ignorer —", "nom": "Raison sociale", "siret": "SIRET / SIREN", "code_postal": "Code postal", "ville": "Ville",
    "naf": "Code NAF", "effectif": "Effectif", "contact": "Nom du contact", "prenom": "Prénom du contact",
    "fonction": "Fonction", "email": "E-mail", "telephone": "Téléphone", "site_web": "Site web", "linkedin": "LinkedIn",
}
SYNONYMES = {
    "nom": r"raison|soci[ée]t[ée]|entreprise|company|denomination",
    "siret": r"siret|siren",
    "code_postal": r"code.?postal|^cp$|zip",
    "ville": r"ville|commune|city|localit",
    "naf": r"naf|ape",
    "effectif": r"effectif|salari|employ",
    "prenom": r"pr[ée]nom|first",
    "contact": r"^contact|nom.?contact|interlocuteur|^nom$|last",
    "fonction": r"fonction|poste|titre|job",
    "email": r"mail",
    "telephone": r"t[ée]l|phone|portable",
    "site_web": r"site|web|url",
    "linkedin": r"linkedin",
}
CHAMPS_HISTORIQUE = {
    "": "— ignorer —", "siren": "SIREN", "nom_client": "Raison sociale", "prestation": "Prestation", "date_session": "Date de session",
    "nb_stagiaires": "Nombre de stagiaires", "formateur": "Formateur", "reference_planif_st": "Référence Planif ST",
}
SYNONYMES_HISTO = {
    "siren": r"siren|siret", "nom_client": r"raison|client|soci[ée]t[ée]|entreprise", "prestation": r"prestation|formation|intitul",
    "date_session": r"date", "nb_stagiaires": r"stagiaire|participant|nombre", "formateur": r"formateur|intervenant",
    "reference_planif_st": r"planif|r[ée]f",
}


def luhn(numero: str) -> bool:
    n = re.sub(r"\s", "", numero or "")
    if not re.fullmatch(r"\d{9}|\d{14}", n):
        return False
    if n.startswith("356000000"):  # La Poste : exception connue
        return True
    total = 0
    for i, ch in enumerate(reversed(n)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def lire_fichier(nom: str, contenu: bytes) -> tuple[list[str], list[list[str]]]:
    """Renvoie (en-têtes, lignes) d'un CSV (séparateur et encodage détectés) ou d'un XLSX."""
    if nom.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(contenu), read_only=True, data_only=True).active
        rows = [["" if v is None else (v.strftime("%Y-%m-%d") if isinstance(v, (date, datetime)) else str(v)).strip() for v in r]
                for r in ws.iter_rows(values_only=True)]
    else:
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                texte = contenu.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        premiere = texte.splitlines()[0] if texte else ""
        sep = ";" if premiere.count(";") >= premiere.count(",") else ","
        if premiere.count("\t") > max(premiere.count(";"), premiere.count(",")):
            sep = "\t"
        rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(texte), delimiter=sep)]
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return [], []
    largeur = len(rows[0])
    return rows[0], [(r + [""] * largeur)[:largeur] for r in rows[1:]]


def deviner_correspondance(entetes: list[str], type_: str = "prospects") -> list[str]:
    syn = SYNONYMES if type_ == "prospects" else SYNONYMES_HISTO
    corr, pris = [], set()
    for h in entetes:
        trouve = ""
        for champ, motif in syn.items():
            if champ not in pris and re.search(motif, h or "", re.I):
                trouve = champ
                break
        corr.append(trouve)
        if trouve:
            pris.add(trouve)
    return corr


def _ligne(imp: ImportFichier, r: list[str]) -> dict:
    o = {}
    for i, champ in enumerate(imp.correspondance):
        if champ and i < len(r):
            o[champ] = r[i].strip()
    return o


def _entier(v: str, defaut: int = 0) -> int:
    m = re.search(r"\d+", (v or "").replace(" ", ""))
    return int(m.group()) if m else defaut


def analyser(imp: ImportFichier) -> list[dict]:
    """Contrôle chaque ligne sans rien écrire. Renvoie une liste de {donnees, etat, classe, note, doublon_id}."""
    resultats, vus = [], set()
    for r in imp.lignes:
        o = _ligne(imp, r)
        nom = o.get("nom", "")
        siret = re.sub(r"\s", "", o.get("siret", ""))
        email = o.get("email", "").lower()
        from .texte import normaliser
        n = re.sub(r"[^a-z0-9]+", " ", re.sub(r"\b(sas|sarl|sa|sasu|eurl|sci|snc|et cie|cie)\b", " ", normaliser(nom))).strip()
        doublon = None
        if siret[:9].isdigit() and len(siret) >= 9:
            doublon = Compte.objects.filter(siren=siret[:9]).first()
        if not doublon and n:
            doublon = Compte.objects.filter(nom_normalise=n).first()
        etat, classe, note = "Nouveau", "ok", ""
        if not nom:
            etat, classe, note = "Rejeté", "bad", "raison sociale vide"
        elif doublon:
            etat, classe, note = "Doublon", "", f"déjà présent : {doublon.nom} (complété, pas dupliqué)"
        elif n in vus:
            etat, classe, note = "Doublon", "", "doublon dans le fichier"
        elif email and est_oppose(email):
            etat, classe, note = "Opposé", "bad", "sur la liste d'opposition : contact non importé"
        elif siret and not luhn(siret):
            etat, classe, note = "À vérifier", "warn", "SIRET invalide : rapprochement avec l'annuaire par nom et commune"
        elif email and email.split("@")[-1].startswith(regles.DOMAINES_PERSONNELS):
            etat, classe, note = "À vérifier", "warn", "e-mail personnel : à remplacer par une adresse professionnelle"
        elif not (o.get("contact") or o.get("prenom")):
            etat, classe, note = "Nouveau", "info", "sans contact : à enrichir"
        vus.add(n)
        resultats.append({"donnees": o, "etat": etat, "classe": classe, "note": note, "doublon_id": doublon.pk if doublon else None})
    return resultats


@transaction.atomic
def appliquer(imp: ImportFichier, utilisateur=None) -> dict:
    res = analyser(imp)
    crees = completes = 0
    for x in res:
        o = x["donnees"]
        if x["etat"] in ("Rejeté", "Opposé") or (x["etat"] == "Doublon" and not x["doublon_id"]):
            continue
        siret = re.sub(r"\s", "", o.get("siret", ""))
        valide = luhn(siret)
        if x["doublon_id"]:
            c = Compte.objects.get(pk=x["doublon_id"])
            completes += 1
        else:
            nom = o.get("nom", "")
            if nom.isupper():
                nom = re.sub(r"(^|[\s\-'])(\w)", lambda m: m.group(1) + m.group(2).upper(), nom.lower())
            naf = o.get("naf", "").replace(" ", "")
            if re.fullmatch(r"\d{4}[A-Z]", naf):
                naf = naf[:2] + "." + naf[2:]
            c = Compte(
                nom=nom, siret=siret if valide and len(siret) == 14 else "", siren=siret[:9] if valide else "",
                code_postal=o.get("code_postal", "")[:5], ville=o.get("ville", ""), naf=naf, segment=regles.segment_depuis_naf(naf),
                effectif=_entier(o.get("effectif", ""), 20) or 20, site_web=o.get("site_web", "") if o.get("site_web", "").startswith("http") else "",
                statut="À qualifier" if x["etat"] == "À vérifier" else "Nouveau", source=f"Import {imp.nom_fichier}", import_fichier=imp,
            )
            c.save()
            crees += 1
            Activite.objects.create(compte=c, type="systeme", texte=f"Créé par l'import « {imp.nom_fichier} ».", utilisateur=utilisateur)
        nom_contact, prenom = o.get("contact", "").strip(), o.get("prenom", "").strip()
        if nom_contact and not prenom and " " in nom_contact:
            prenom, nom_contact = nom_contact.split(" ", 1)
        if nom_contact or prenom:
            email = o.get("email", "").lower()
            perso = email.split("@")[-1].startswith(regles.DOMAINES_PERSONNELS) if email else False
            complet = f"{prenom} {nom_contact}".strip().lower()
            existe = any((email and k.email.lower() == email) or k.nom_complet.lower() == complet for k in c.contacts.all())
            if not existe:
                fonction = o.get("fonction", "")
                Contact.objects.create(
                    compte=c, prenom=prenom, nom=nom_contact or prenom, fonction=fonction,
                    role="decideur" if re.search(r"qse|hse|drh|dir|g[ée]rant|responsable|pr[ée]sident", fonction, re.I) else "utilisateur",
                    email="" if perso else email, statut_email="probable" if email and not perso else "absent",
                    telephone=o.get("telephone", ""), linkedin_url=o.get("linkedin", "") if o.get("linkedin", "").startswith("http") else "",
                )
        recalculer(c)
    imp.applique_le = timezone.now()
    imp.rapport = {"crees": crees, "completes": completes, "lignes": len(res),
                   "rejetes": sum(1 for x in res if x["etat"] in ("Rejeté", "Opposé"))}
    imp.importe_par = utilisateur
    imp.save()
    return imp.rapport


@transaction.atomic
def annuler(imp: ImportFichier) -> int:
    n = imp.comptes.count()
    imp.comptes.all().delete()
    imp.annule_le = timezone.now()
    imp.save(update_fields=["annule_le"])
    return n


def _date(v: str) -> date | None:
    v = (v or "").strip()
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(v[:10], f).date()
        except ValueError:
            continue
    return None


def _prestation(v: str) -> str | None:
    from .texte import normaliser
    n = normaliser(v)
    if "mac" in n or "recycl" in n:
        return "MAC SST"
    if "sst" in n or "secour" in n:
        return "SST initial"
    if "evacu" in n:
        return "Exercice d'évacuation"
    if "extinct" in n or "incendie" in n or "feu" in n:
        return "Manipulation des extincteurs"
    if "geste" in n or "posture" in n or "tms" in n:
        return "Gestes et postures"
    return None


@transaction.atomic
def appliquer_historique(imp: ImportFichier) -> dict:
    crees, rejets = 0, []
    for i, r in enumerate(imp.lignes, start=2):
        o = _ligne(imp, r)
        d, pr = _date(o.get("date_session", "")), _prestation(o.get("prestation", ""))
        if not d or not pr or not o.get("nom_client"):
            rejets.append(i)
            continue
        siren = re.sub(r"\D", "", o.get("siren", ""))[:9]
        compte = (Compte.objects.filter(siren=siren).first() if siren else None)
        if not compte:
            from .texte import normaliser
            n = re.sub(r"[^a-z0-9]+", " ", normaliser(o["nom_client"])).strip()
            compte = Compte.objects.filter(nom_normalise=n).first()
        HistoriqueFormation.objects.create(
            compte=compte, siren=siren, nom_client=o["nom_client"], prestation=pr, date_session=d,
            nb_stagiaires=_entier(o.get("nb_stagiaires", ""), 1) or 1, formateur=o.get("formateur", ""),
            reference_planif_st=o.get("reference_planif_st", ""), source="import",
        )
        crees += 1
    imp.applique_le = timezone.now()
    imp.rapport = {"crees": crees, "rejets": rejets}
    imp.save()
    return imp.rapport
