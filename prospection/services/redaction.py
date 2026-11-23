"""Rédaction assistée (cahier des charges §3.6).

Deux moteurs :
- modèles intégrés (sans IA, immédiats, toujours disponibles) : mêmes textes que la maquette ;
- IA Claude (si ANTHROPIC_API_KEY est présente) : réécrit le message à partir des faits de la fiche,
  sans rien inventer. En cas d'échec, on garde le modèle intégré.
Le pied de page RGPD est toujours ajouté par le code, jamais par l'IA.
"""

from __future__ import annotations

import logging
import os

from django.conf import settings
from pydantic import BaseModel, Field

from .. import regles
from ..models import Compte, Contact
from .rgpd import mention_information
from .scoring import besoin

log = logging.getLogger("prospection.redaction")

CANAUX = [("email", "E-mail"), ("linkedin", "LinkedIn"), ("appel", "Script d'appel"), ("relance", "Relance")]
TONS = [("direct", "Direct"), ("institutionnel", "Institutionnel (public)"), ("chaleureux", "Chaleureux (client)")]

PREUVE = ("Nous intervenons partout en France avec un interlocuteur unique, des formateurs sapeurs-pompiers "
          "et une unité mobile de formation incendie.")
UMFI = ("Notre unité mobile (UMFI) se déplace sur votre parking : extinction sur feux réels au bac à flammes, "
        "sans immobiliser vos équipes plus d'une demi-journée.")
SIGNATURE = "\n\n[Prénom Nom]\nFORMA'ST – Formation santé et sécurité au travail\n[Téléphone]"


def _accroche(c: Compte, g) -> str:
    seg = regles.SEGMENTS.get(c.segment, regles.SEGMENTS["autre"])["libelle"].lower()
    if not g:
        return f"Dans le secteur {seg}, les obligations de formation sécurité (SST, incendie, manutention) pèsent lourd quand les équipes tournent."
    t = g.type
    if t == "site":
        return (f"J'ai vu que {c.nom} ouvre un nouvel établissement. Avant l'arrivée des équipes, c'est le bon moment pour organiser "
                "la formation sécurité : sauveteurs secouristes, consignes incendie et exercice d'évacuation propres au nouveau bâtiment.")
    if t == "qse":
        return (f"Vous recrutez un(e) responsable HSE : la prévention prend de l'ampleur chez {c.nom}. Nous pouvons prendre en charge "
                "les formations obligatoires dès maintenant, puis travailler avec votre futur(e) responsable.")
    if t == "recrut":
        return ("Avec de nombreux postes ouverts en ce moment, vous allez accueillir beaucoup de nouveaux salariés. Former à l'accueil "
                "sécurité et aux gestes et postures dès les premières semaines réduit nettement les accidents.")
    if t == "dirigeant":
        return "Vous avez récemment pris vos fonctions : c'est souvent l'occasion de faire le point sur les formations obligatoires et leurs échéances."
    if t == "marche":
        return ("Votre marché de formation sécurité arrive bientôt à échéance. Nous aimerions comprendre vos besoins et vos retours "
                "d'expérience avant la rédaction du prochain cahier des charges.")
    if t == "ao":
        return (f"{c.nom} lance régulièrement des consultations liées à la sécurité. Nous intervenons auprès des organismes publics "
                "pour les formations SST, incendie et évacuation, en bons de commande ou en accord-cadre.")
    if t == "mac":
        return f"{g.texte} : sans recyclage (MAC SST), les certificats ne sont plus valables."
    if t == "presse":
        return (f"J'ai lu l'annonce : {g.texte[:1].lower() + g.texte[1:]}. Une telle évolution s'accompagne presque toujours "
                "de nouvelles équipes à former et de consignes de sécurité à revoir.")
    if t == "web":
        return "Merci de l'intérêt que vous portez à nos contenus sur la prévention. Les mêmes questions reviennent souvent : qui guide, qui vérifie, comment évacuer."
    if t == "linkedin":
        return f"J'ai vu votre actualité sur LinkedIn. {c.nom} évolue, et les formations sécurité suivent souvent ces changements."
    return "La sécurité de vos équipes est un sujet que nous suivons de près dans votre secteur."


def _besoin_txt(c: Compte, b: dict) -> str:
    t = (f"Pour un effectif d'environ {c.effectif} personnes, l'INRS recommande {b['sst']} sauveteurs secouristes du travail, "
         f"soit {b['sessions_sst']} session{'s' if b['sessions_sst'] > 1 else ''}, puis un recyclage tous les 24 mois.")
    t += (" Les exercices d'évacuation sont aussi à organiser tous les 6 mois"
          + (", un point sensible pour un site classé ICPE" if c.icpe else ", avec un public à guider" if c.erp else "") + ".")
    if b["opco_finance"]:
        t += f" Avec moins de 50 salariés, ces formations sont en général finançables par votre {c.opco or 'OPCO'}."
    return t


def generer(c: Compte, contact: Contact | None, canal: str = "email", ton: str = "direct", consigne: str = "") -> dict:
    """Message à partir des modèles intégrés. Renvoie {objet, texte}."""
    b = besoin(c)
    g = c.signal_principal()
    court = "court" in consigne.lower()
    umfi = any(m in consigne.lower() for m in ("umfi", "mobile", "camion"))
    nom = contact.nom_complet if contact and contact.role != "standard" else ""
    salut = "Madame, Monsieur," if ton == "institutionnel" else (f"Bonjour {nom}," if nom else "Bonjour,")

    if canal == "email":
        objets = {"site": "Formation sécurité de votre nouveau site", "qse": "Votre recrutement HSE et les formations obligatoires",
                  "recrut": "Accueil sécurité de vos nouveaux salariés", "dirigeant": "Vos formations sécurité : le point à votre arrivée",
                  "marche": "Votre prochain marché de formation sécurité", "mac": "Échéance MAC SST de vos salariés",
                  "presse": f"{c.nom} : former les nouvelles équipes"}
        objet = objets.get(g.type if g else "", f"Formations SST et incendie pour {c.nom}")
        corps = f"{salut}\n\n{_accroche(c, g)}"
        if not court:
            corps += f"\n\n{_besoin_txt(c, b)}"
        if umfi:
            corps += f"\n\n{UMFI}"
        if not court and ton != "direct":
            corps += f"\n\n{PREUVE}"
        corps += ("\n\nSeriez-vous disponible pour un échange de 20 minutes, dans le cadre de votre sourçage ?" if g and g.type == "marche"
                  else "\n\nSeriez-vous disponible 15 minutes la semaine prochaine pour en parler ?")
        corps += ("\n\nJe vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées." if ton == "institutionnel"
                  else "\n\nBien cordialement,")
        return {"objet": objet, "texte": corps + SIGNATURE + mention_information(c.source)}

    if canal == "linkedin":
        prenom = contact.prenom if contact and contact.prenom else (nom.split(" ")[0] if nom else "")
        courts = {"site": f"Je vois que {c.nom} ouvre un nouveau site : nous formons les équipes avant l'ouverture (SST, incendie, évacuation).",
                  "qse": f"Je vois que vous renforcez la prévention chez {c.nom}.", "recrut": f"Je vois que {c.nom} recrute beaucoup en ce moment.",
                  "dirigeant": "Félicitations pour votre prise de fonction.", "presse": f"J'ai lu l'actualité de {c.nom}, félicitations.",
                  "mac": "Les certificats SST de vos équipes arrivent à échéance.", "linkedin": "Votre publication m'a intéressé."}
        t = (f"Bonjour{' ' + prenom if prenom else ''}, je travaille chez FORMA'ST (formation SST, incendie, gestes et postures). "
             f"{courts.get(g.type if g else '', '')} Ravi d'échanger si le sujet vous concerne.").replace("  ", " ")
        return {"objet": "Invitation LinkedIn (à envoyer vous-même)", "texte": t[:300]}

    if canal == "appel":
        raison = {"site": "vous ouvrez un nouvel établissement", "qse": "vous recrutez un responsable HSE",
                  "mac": "les certificats SST de vos salariés arrivent à échéance", "recrut": "vous recrutez beaucoup en ce moment"}
        motif = f"Je vous appelle parce que {raison.get(g.type, 'nous avons vu votre actualité')}." if g else "Je vous appelle au sujet des formations sécurité obligatoires."
        t = f"""OUVERTURE (20 s)
« Bonjour{' ' + nom if nom else ''}, [Prénom] de FORMA'ST, organisme de formation santé-sécurité. {motif} Vous avez deux minutes ? »

DÉCOUVERTE
1. Combien de sauveteurs secouristes avez-vous aujourd'hui, et quand ont-ils été formés ?
2. À quand remonte votre dernier exercice d'évacuation ? Qui joue le rôle de guide et de serre-file ?
3. Qui décide et qui finance les formations (RH, QSE, direction de site, OPCO) ?

BESOIN ESTIMÉ À ÉVOQUER
{b['sst']} SST recommandés ({b['sessions_sst']} session{'s' if b['sessions_sst'] > 1 else ''}), {b['exercices']} exercices d'évacuation par an, {b['manutention']} salariés exposés à la manutention.

OBJECTIONS
· « On a déjà un prestataire » → « Très bien. Quand se termine le contrat ? Je vous propose une session pilote pour comparer. »
· « Pas de budget » → « {'Avec moins de 50 salariés, votre OPCO finance en général ces formations.' if b['opco_finance'] else "Le SST et les exercices sont obligatoires ; nous pouvons étaler sur l'année."} »
· « On le fait en interne » → « Avez-vous un formateur habilité INRS ? Sinon, les certificats ne sont pas valables. »
· « Envoyez-moi une documentation » → « Avec plaisir. Pour l'adapter, combien de sites et de salariés sont concernés ? »
· « Rappelez plus tard » → « Bien sûr. Plutôt début ou fin de mois ? »
· « Ce n'est pas moi » → « Qui s'en occupe chez vous ? Je peux dire que je viens de votre part ? »

CONCLUSION
Proposer un rendez-vous de 30 minutes (Teams ou sur site) et deux créneaux précis."""
        return {"objet": "Script d'appel", "texte": t}

    # relance
    sites = f"un réseau de {c.nb_etablissements} sites" if c.nb_etablissements > 1 else "un site"
    t = (f"{salut}\n\nJe reviens vers vous avec un élément concret : pour {sites} comme le vôtre, nous organisons en général "
         f"{b['sessions_sst']} session{'s' if b['sessions_sst'] > 1 else ''} SST et {b['exercices']} exercices d'évacuation par an, "
         "avec un seul interlocuteur et des dates calées sur vos plannings.\n\nEst-ce le bon moment pour en parler, ou préférez-vous "
         "que je revienne vers vous au premier trimestre ?\n\nBien cordialement,")
    return {"objet": "RE: " + (regles.SIGNAUX[g.type]["libelle"] if g else "Formations sécurité"), "texte": t + SIGNATURE + mention_information(c.source)}


def brief(c: Compte) -> str:
    b = besoin(c)
    g = c.signal_principal()
    seg = regles.SEGMENTS.get(c.segment, regles.SEGMENTS["autre"])["libelle"].lower()
    risques = {"logistique": "manutention, engins, quais, rotation du personnel", "sante": "TMS des soignants, RPS, évacuation de personnes non autonomes",
               "industrie": "machines, incendie, produits", "commerce": "public, manutention en réserve, personnel jeune",
               "collectivite": "agents techniques, ERP communaux", "btp": "chantiers, chutes, manutention"}.get(c.segment, "accueil du public, horaires décalés")
    lignes = [
        f"{c.nom} ({c.ville or '?'}{', ' + c.departement if c.departement else ''}) : {seg}, NAF {c.naf or '?'}, environ {c.effectif} salariés"
        + (f" sur {c.nb_etablissements} sites" if c.nb_etablissements > 1 else "") + f". Source : {c.source or 'saisie'}.",
        f"Risques métier : {risques}" + (" ; site ICPE (risque incendie renforcé)" if c.icpe else "") + ".",
        f"Obligations : {b['sst']} SST recommandés, MAC tous les 24 mois, exercices d'évacuation tous les 6 mois, manutention pour environ {b['manutention']} salariés.",
        f"Signal : {g.texte} ({g.source}, il y a {g.age_jours} j)." if g else "Signal : aucun. À travailler sur le segment ou à garder en nurturing.",
        f"Potentiel estimé : {b['potentiel_an1']:,} € la première année (tarifs {b['tarifs']['source']}).".replace(",", " "),
    ]
    return "\n".join(lignes)


# ------------------------------------------------------------------------ IA (optionnelle)


class MessageIA(BaseModel):
    objet: str = Field(description="Objet de l'e-mail, 70 caractères au plus (vide pour LinkedIn ou un script)")
    texte: str = Field(description="Corps du message, sans pied de page RGPD")
    champs_a_completer: list[str] = Field(description="Informations manquantes signalées [À COMPLÉTER : …]")


REGLES_IA = """Tu rédiges pour FORMA'ST, organisme de formation en santé et sécurité au travail (SST, MAC SST, incendie et évacuation,
UMFI, gestes et postures, QVT / RPS), Qualiopi et habilité INRS SST, qui intervient partout en France.
Règles absolues :
1. N'invente rien : aucun chiffre, nom, référence client ou fait absent des DONNÉES. Sinon écris [À COMPLÉTER : …].
2. Vouvoiement, français courant, phrases courtes, pas de superlatifs ni de « je me permets ».
3. Mots interdits : gratuit, urgent, promo, exceptionnel, garanti, points d'exclamation multiples.
4. Une seule question d'appel à l'action.
5. Ne mentionne jamais un accident du travail, une visite du site web ou une ouverture d'e-mail.
6. E-mail : 60 à 170 mots. LinkedIn : 300 caractères au plus, sans lien. Script d'appel : ouverture 20 s, 3 questions, objections, conclusion.
7. N'ajoute pas de mention RGPD ni de signature : le logiciel les ajoute."""


def ia_disponible() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


class BudgetIAAtteint(Exception):
    pass


def rediger_ia(c: Compte, contact: Contact | None, canal: str, ton: str, consigne: str, client=None, utilisateur=None) -> dict:
    import anthropic

    from ..models import ProfilEntreprise
    from . import couts_ia

    if couts_ia.budget_atteint():
        raise BudgetIAAtteint("Budget IA du mois atteint : l'IA reprendra le mois prochain (ou relevez le budget dans « Coûts IA »).")

    base = generer(c, contact, canal, ton, consigne)
    donnees = (f"FICHE :\n{brief(c)}\n\nCONTACT : {contact.nom_complet + ', ' + contact.fonction if contact else 'inconnu'}\n"
               f"CANAL : {canal} · TON : {ton}\nCONSIGNE : {consigne or 'aucune'}\n\nPROPOSITION DE DÉPART :\n{base['texte'].split(chr(10) + '—' + chr(10))[0]}")
    client = client or anthropic.Anthropic()
    rep = client.beta.messages.parse(
        model=settings.CLAUDE_MODEL,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low"},
        system=[{"type": "text", "text": f"{ProfilEntreprise.get().texte_pour_ia()}\n\n{REGLES_IA}", "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"Améliore ce message en respectant les règles.\n\n{donnees}"}],
        output_format=MessageIA,
    )
    couts_ia.enregistrer(rep, "redaction", c, utilisateur)
    if rep.parsed_output is None:
        raise RuntimeError(f"Réponse IA incomplète ({rep.stop_reason}).")
    m: MessageIA = rep.parsed_output
    texte = m.texte.strip()
    if canal in ("email", "relance"):
        texte += SIGNATURE + mention_information(c.source)
    if canal == "linkedin":
        texte = texte[:300]
    return {"objet": m.objet or base["objet"], "texte": texte, "ia": True}
