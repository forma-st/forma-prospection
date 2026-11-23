"""Outils texte : normalisation et recherche de mots-clés sans accents ni casse."""

import html
import re
import unicodedata


def normaliser(texte: str) -> str:
    """Minuscule, sans accents, apostrophes et tirets ramenés à des espaces."""
    if not texte:
        return ""
    texte = html.unescape(texte)
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.lower()
    texte = re.sub(r"[’'`\-_/]", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


def _motif(mot_cle: str) -> re.Pattern:
    mot = normaliser(mot_cle)
    # "*" en fin de mot = troncature (ex. "secour*" couvre secours, secouriste)
    if mot.endswith("*"):
        return re.compile(r"\b" + re.escape(mot[:-1]) + r"\w*")
    return re.compile(r"\b" + re.escape(mot) + r"\b")


def mots_cles_trouves(texte: str, mots_cles: list[str]) -> list[str]:
    """Renvoie les mots-clés (forme d'origine) présents dans le texte."""
    norm = normaliser(texte)
    return [m for m in mots_cles if _motif(m).search(norm)]
