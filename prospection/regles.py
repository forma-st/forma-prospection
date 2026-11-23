"""Règles métier par défaut (cahier des charges §3.2 à §3.4, §3.17 ; kit : regles/regles_metier.json).

Les poids du score, les seuils des paliers, la part de SST et les départements prioritaires
sont modifiables dans l'administration (modèle Parametres). Le reste est ici.
"""

SEGMENTS = {
    "logistique": {"libelle": "Logistique et transport", "poids": 30, "manutention": 0.6},
    "sante": {"libelle": "Santé et médico-social", "poids": 28, "manutention": 0.5},
    "industrie": {"libelle": "Industrie", "poids": 28, "manutention": 0.4},
    "commerce": {"libelle": "Commerce multi-sites", "poids": 26, "manutention": 0.3},
    "collectivite": {"libelle": "Collectivités et bailleurs", "poids": 22, "manutention": 0.25},
    "hotellerie": {"libelle": "Hôtellerie-restauration", "poids": 18, "manutention": 0.3},
    "btp": {"libelle": "BTP", "poids": 18, "manutention": 0.5},
    "prescripteur": {"libelle": "Prescripteur", "poids": 10, "manutention": 0.0},
    "autre": {"libelle": "Autre", "poids": 12, "manutention": 0.2},
}
SEGMENT_CHOICES = [(k, v["libelle"]) for k, v in SEGMENTS.items()]

SIGNAUX = {
    "site": {"libelle": "Nouvel établissement", "poids": 35, "demi_vie": 60},
    "qse": {"libelle": "Recrutement QSE / HSE", "poids": 30, "demi_vie": 30},
    "recrut": {"libelle": "Recrutement en nombre", "poids": 20, "demi_vie": 30},
    "dirigeant": {"libelle": "Nouveau décideur", "poids": 20, "demi_vie": 90},
    "marche": {"libelle": "Marché public à renouveler", "poids": 40, "demi_vie": 180},
    "ao": {"libelle": "Acheteur public actif", "poids": 15, "demi_vie": 120},
    "mac": {"libelle": "MAC SST à échéance", "poids": 50, "demi_vie": 90},
    "presse": {"libelle": "Actualité", "poids": 25, "demi_vie": 45},
    "web": {"libelle": "Intérêt sur le site web", "poids": 25, "demi_vie": 14},
    "linkedin": {"libelle": "Activité LinkedIn (changement de poste, publication)", "poids": 20, "demi_vie": 30},
}
SIGNAL_CHOICES = [(k, v["libelle"]) for k, v in SIGNAUX.items()]

STATUTS = [
    "Nouveau", "À qualifier", "À contacter", "En contact", "A répondu", "RDV fixé",
    "Transmis au CRM", "Client", "Pas maintenant", "Écarté", "Opposé",
]
STATUT_CHOICES = [(s, s) for s in STATUTS]
STATUTS_INACTIFS = {"Client", "Écarté", "Opposé"}

ROLES = [("decideur", "Décideur"), ("prescripteur", "Prescripteur"), ("utilisateur", "Utilisateur"), ("standard", "Standard")]
STATUTS_EMAIL = [("verifie", "Vérifié"), ("probable", "Probable"), ("absent", "À trouver"), ("invalide", "Invalide")]

# Échéances des formations réalisées : (mois, relance N jours avant)
ECHEANCES = {
    "SST initial": (24, 90),
    "MAC SST": (24, 90),
    "Exercice d'évacuation": (6, 30),
    "Manipulation des extincteurs": (12, 45),
    "Gestes et postures": (24, 60),
}
PRESTATION_CHOICES = [(k, k) for k in ECHEANCES]

# Tarifs d'exemple (session intra) si le catalogue de l'outil AO est vide
TARIFS_DEFAUT = {"sst": 1450, "gp": 980, "incendie": 690}

# Tranches d'effectif INSEE -> effectif estimé (milieu de tranche)
TRANCHES = {
    "00": 0, "01": 2, "02": 4, "03": 8, "11": 15, "12": 35, "21": 75, "22": 150,
    "31": 225, "32": 375, "41": 750, "42": 1500, "51": 3500, "52": 7500, "53": 10000,
}

MOTS_INTERDITS = ["gratuit", "urgent", "promo", "exceptionnel", "garanti", "!!"]
DOMAINES_PERSONNELS = ("gmail.", "hotmail.", "yahoo.", "orange.", "free.", "wanadoo.", "outlook.", "laposte.", "sfr.", "icloud.")


def segment_depuis_naf(naf: str) -> str:
    n = (naf or "").replace(".", "")
    if n[:2] in ("49", "52", "53"):
        return "logistique"
    if n[:2] in ("86", "87", "88"):
        return "sante"
    if n[:2].isdigit() and (10 <= int(n[:2]) <= 33):
        return "industrie"
    if n[:2] in ("46", "47"):
        return "commerce"
    if n[:2] == "84" or n.startswith("6820") or n.startswith("9311"):
        return "collectivite"
    if n[:2] in ("55", "56"):
        return "hotellerie"
    if n[:2] in ("41", "42", "43"):
        return "btp"
    if n.startswith("6920") or n.startswith("7022"):
        return "prescripteur"
    return "autre"
