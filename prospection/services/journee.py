"""« Ma journée » : prochaines actions classées (cahier des charges §3.18)."""

from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from .. import regles
from ..models import Compte, HistoriqueFormation, Message, ReportAction, Tache


@dataclass
class Action:
    cle: str
    icone: str
    titre: str
    sous_titre: str
    raison: str
    priorite: float
    url: str
    bouton: str
    chaud: bool = False
    tache_id: int | None = None
    historique_id: int | None = None


def court(c: Compte) -> str:
    g = c.signal_principal()
    k = c.contact_principal()
    t = f"Palier {c.palier} ({c.score})"
    if g:
        t += f" · {regles.SIGNAUX[g.type]['libelle'].lower()} il y a {g.age_jours} j"
    t += f" · {(k.fonction or 'contact').lower()}" if k else " · aucun contact"
    return t


def actions(utilisateur) -> list[Action]:
    aujourd_hui = timezone.localdate()
    masquees = set(ReportAction.objects.filter(utilisateur=utilisateur, jour=aujourd_hui).values_list("cle", flat=True))
    liste: list[Action] = []

    for r in Message.objects.filter(sens="entrant", traite=False).select_related("compte", "contact")[:30]:
        liste.append(Action(
            cle=f"r{r.pk}", icone="reponses", titre=f"Traiter la réponse de {r.contact or r.expediteur}", sous_titre=r.compte.nom if r.compte else "",
            raison=f"Classée « {r.get_classe_display()} » ({r.confiance} %) : {r.objet}", priorite=100 if r.classe == "interesse" else 85,
            url=f"/prospection/reponses/?id={r.pk}", bouton="Traiter", chaud=r.classe == "interesse",
        ))
    n_valider = Message.objects.filter(sens="sortant", statut="a_valider").count()
    if n_valider:
        liste.append(Action(cle="valider", icone="email", titre=f"Valider {n_valider} e-mail{'s' if n_valider > 1 else ''} préparé{'s' if n_valider > 1 else ''} par les séquences",
                            sous_titre="Messagerie", raison="Relisez, corrigez si besoin, puis validez : ils partiront dans la prochaine plage d'envoi.",
                            priorite=88, url="/prospection/messagerie/?onglet=a_valider", bouton="Relire et valider"))

    for t in Tache.objects.filter(faite_le__isnull=True, echeance__lte=aujourd_hui).select_related("compte"):
        if t.assignee_id and t.assignee_id != utilisateur.pk:
            continue
        canal = {"appel": "appel", "linkedin": "linkedin", "email": "email"}.get(t.type, "email")
        url = f"/prospection/compte/{t.compte_id}/?canal={canal}" if t.compte_id else "/prospection/taches/"
        liste.append(Action(
            cle=f"t{t.pk}", icone=t.type, titre=t.titre, sous_titre=t.compte.nom if t.compte else "",
            raison=(f"En retard de {t.retard} j" if t.retard > 0 else "Aujourd'hui") + (f" · {court(t.compte)}" if t.compte else ""),
            priorite=90 if t.retard > 0 else 80, url=url, bouton="Ouvrir avec le texte", chaud=t.retard > 0, tache_id=t.pk,
        ))

    for h in HistoriqueFormation.objects.filter(relance_creee=False).select_related("compte"):
        if h.etat == "ok":
            continue
        liste.append(Action(
            cle=f"h{h.pk}", icone="clock", titre=f"Relancer {h.nom_client} : {h.prestation}",
            sous_titre=f"{h.nb_stagiaires} stagiaire{'s' if h.nb_stagiaires > 1 else ''}",
            raison=f"Échéance {h.echeance:%d/%m/%Y} ({'dépassée' if h.jours_restants < 0 else f'dans {h.jours_restants} j'}).",
            priorite=75, url="/prospection/historique/", bouton="Créer la relance", chaud=h.etat == "retard", historique_id=h.pk,
        ))

    prospects = (Compte.objects.filter(palier="A", statut__in=["Nouveau", "À qualifier", "À contacter"])
                 .prefetch_related("signaux", "contacts"))
    for c in prospects:
        if not any(s.actif for s in c.signaux.all()):
            continue
        liste.append(Action(
            cle=f"p{c.pk}", icone="spark", titre=f"Premier contact : {c.nom}", sous_titre=c.ville,
            raison=court(c), priorite=60 + c.score / 10, url=f"/prospection/compte/{c.pk}/", bouton="Rédiger",
        ))

    return sorted((a for a in liste if a.cle not in masquees), key=lambda a: -a.priorite)


def faites_aujourd_hui(utilisateur) -> int:
    return ReportAction.objects.filter(utilisateur=utilisateur, jour=timezone.localdate(), faite=True).count()
