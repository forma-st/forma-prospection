# Code réutilisable issu de l'outil AO (Veille AO)

Copies de référence, à adapter dans l'application cible :

| Fichier | Rôle | À adapter |
|---|---|---|
| `http.py` | Appels HTTP avec nouvelles tentatives (httpx) | Rien |
| `texte.py` | Normalisation de texte (accents, casse, HTML) pour le dédoublonnage et les mots-clés | Rien |
| `annuaire.py` | Recherche et mise à jour depuis l'API publique Recherche d'entreprises (SIREN, NAF, tranche d'effectif, adresse, dirigeants, TVA) | Remplace le modèle `Entreprise` de l'outil AO par le `Compte` de l'agent ; ajouter IDCC, nombre d'établissements, coordonnées |

API publique, gratuite, sans clé : https://recherche-entreprises.api.gouv.fr/docs/
