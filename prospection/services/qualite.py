"""Contrôle avant envoi (cahier des charges §3.18). Même logique que le contrôle en direct de la page."""

from __future__ import annotations

import re

from .. import regles

MOTS_SIGNAL = {
    "site": r"établissement|ouvr|bâtiment", "qse": r"HSE|QSE|prévention", "recrut": r"recrut|postes|nouveaux salariés",
    "dirigeant": r"fonction", "marche": r"marché", "ao": r"consultation", "mac": r"MAC|recyclage",
    "presse": r"annonce|évolution", "web": r"guide", "linkedin": r"LinkedIn|poste|publication",
}


def controler(texte: str, canal: str, compte=None) -> dict | None:
    if canal == "appel":
        return None
    controles = []
    corps = texte.split("\n—\n")[0]
    if canal == "linkedin":
        controles.append((len(texte) <= 300, f"{len(texte)} / 300 caractères"))
        controles.append((not re.search(r"https?://", texte), "Pas de lien dans une invitation"))
        controles.append((bool(re.search(r"Bonjour \S", texte)), "Salutation personnalisée"))
        controles.append((not re.search(r"gratuit|promo|urgent", texte, re.I), "Pas de ton promotionnel"))
    else:
        mots = len(corps.split())
        q = corps.count("?")
        controles.append((60 <= mots <= 170, f"{mots} mots (idéal : 60 à 170)"))
        if compte is not None:
            noms = [compte.nom] + [c.nom_complet for c in compte.contacts.all()]
            controles.append((any(n and n in corps for n in noms), "Personnalisé (entreprise ou contact cité)"))
            g = compte.signal_principal()
            if g:
                controles.append((bool(re.search(MOTS_SIGNAL.get(g.type, "."), corps, re.I)),
                                  f"Accroche sur le signal « {regles.SIGNAUX[g.type]['libelle'].lower()} »"))
        controles.append((q == 1, "Une seule question, claire" if q == 1 else f"{q} questions (en garder une)"))
        controles.append((not any(m in corps.lower() for m in regles.MOTS_INTERDITS), "Pas de mots qui déclenchent les filtres anti-spam"))
        controles.append((bool(re.search(r"ne plus recevoir|STOP|opposition", texte, re.I)), "Mention d'opposition présente"))
        restants = sorted(set(re.findall(r"\[[^\]]+\]", texte)))
        controles.append((not restants, f"À compléter : {', '.join(restants[:3])}" if restants else "Aucun champ à compléter"))
    ok = sum(1 for c in controles if c[0])
    return {"note": round(ok / len(controles) * 100), "controles": controles}
