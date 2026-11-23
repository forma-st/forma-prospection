"""Écrans de l'agent d'aide à la prospection."""

from __future__ import annotations

import re
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import regles
from .models import (Activite, ActionLinkedIn, Compte, ConnexionLinkedIn, Contact, HistoriqueFormation, ImportFichier,
                     Opposition, Parametres, PublicationLinkedIn, ReportAction, Signal, Tache)
from .services import formao, imports, journee as svc_journee, linkedin, qualite, redaction, rgpd, sirene
from .services.texte import normaliser
from .services.scoring import besoin, recalculer, recalculer_tout

def _retour_sur(request, defaut: str) -> str:
    """Adresse de retour envoyée par un formulaire, seulement si elle reste sur ce site."""
    r = request.POST.get("retour") or ""
    return r if r and url_has_allowed_host_and_scheme(r, allowed_hosts={request.get_host()}, require_https=request.is_secure()) else defaut


VUES = [("tous", "Tous"), ("auto", "Trouvés automatiquement"), ("A", "Palier A"), ("signaux", "Avec signal"), ("sanscontact", "Sans contact"),
        ("public", "Acheteurs publics"), ("clients", "Clients")]


def _ctx(request, **kw):
    p = Parametres.get()
    kw.setdefault("parametres", p)
    from .models import Message
    kw["nb_reponses"] = Message.objects.filter(sens="entrant", traite=False).count()
    kw["nb_a_valider"] = Message.objects.filter(sens="sortant", statut="a_valider").count()
    kw["mode_test"] = p.mode_test
    kw["nb_taches"] = Tache.objects.filter(faite_le__isnull=True, echeance__lte=timezone.localdate()).count()
    kw["nb_relances"] = sum(1 for h in HistoriqueFormation.objects.filter(relance_creee=False) if h.etat != "ok")
    kw["linkedin_actif"] = p.linkedin_actif
    return kw


# ------------------------------------------------------------------ Ma journée


@login_required
def journee(request):
    actions = svc_journee.actions(request.user)
    p = Parametres.get()
    faites = svc_journee.faites_aujourd_hui(request.user)
    recents = Signal.objects.select_related("compte").filter(actif=True)[:6]
    from .services.recherche import bilan_nuit
    from .services import couts_ia
    from .models import AppelIA
    return render(request, "prospection/journee.html", _ctx(
        request, couts=couts_ia.mois_en_cours() if (redaction.ia_disponible() or AppelIA.objects.exists()) else None,
        actions=actions[:12], reste=max(0, len(actions) - 12), total=len(actions), faites=faites,
        objectif=p.objectif_actions_jour, pct=min(100, round(faites / max(1, p.objectif_actions_jour) * 100)), signaux=recents,
        nb_a=Compte.objects.filter(palier="A").exclude(statut__in=regles.STATUTS_INACTIFS).count(), bilan=bilan_nuit(), saison=regles.SAISONS[timezone.localdate().month],
        nb_actifs=Compte.objects.exclude(statut__in=regles.STATUTS_INACTIFS).count(),
    ))


@login_required
@require_POST
def journee_action(request):
    cle, quoi = request.POST.get("cle", ""), request.POST.get("quoi", "")
    ReportAction.objects.update_or_create(utilisateur=request.user, cle=cle, jour=timezone.localdate(), defaults={"faite": quoi == "fait"})
    if quoi == "fait" and cle.startswith("t"):
        Tache.objects.filter(pk=cle[1:]).update(faite_le=timezone.now())
    messages.success(request, "Bien joué. Action suivante en tête de liste." if quoi == "fait" else "Reporté à demain.")
    return redirect("prospection:journee")


# ------------------------------------------------------------------ Prospects


def _filtrer(request):
    qs = Compte.objects.prefetch_related("signaux", "contacts")
    g = request.GET
    vue = g.get("vue", "tous")
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(ville__icontains=q) | Q(naf__icontains=q) | Q(siren__icontains=q) | Q(contacts__nom__icontains=q)).distinct()
    if g.get("palier") or vue == "A":
        qs = qs.filter(palier=g.get("palier") or "A")
    if g.get("segment") or vue == "public":
        qs = qs.filter(segment=g.get("segment") or "collectivite")
    if g.get("statut"):
        qs = qs.filter(statut=g["statut"])
    elif vue == "clients":
        qs = qs.filter(Q(est_client=True) | Q(statut="Client"))
    elif not g.get("tout"):
        qs = qs.exclude(statut__in=["Écarté", "Opposé"])
    if g.get("departement"):
        qs = qs.filter(departement=g["departement"])
    if vue == "signaux":
        qs = qs.filter(signaux__actif=True).distinct()
    if vue == "auto":
        qs = qs.filter(source__startswith="Recherche auto")
    comptes = list(qs.order_by("-score", "nom")[:500])
    if vue == "sanscontact":
        comptes = [c for c in comptes if not c.contact_principal() or c.contact_principal().role == "standard"]
    return comptes, vue


@login_required
def prospects(request):
    comptes, vue = _filtrer(request)
    from .models import Sequence
    deps = sorted(d for d in Compte.objects.values_list("departement", flat=True).distinct() if d)
    affichage = request.GET.get("affichage", "")
    q = request.GET.copy()
    q.pop("affichage", None)
    colonnes = [(st, [c for c in comptes if c.statut == st]) for st in ["Nouveau", "À qualifier", "À contacter", "En contact", "A répondu", "RDV fixé", "Transmis au CRM"]]
    return render(request, "prospection/prospects.html", _ctx(
        request, comptes=comptes, vue=vue, vues=VUES, segments=regles.SEGMENT_CHOICES, statuts=regles.STATUTS, departements=deps, g=request.GET,
        affichage=affichage, qs_sans_affichage=q.urlencode(), colonnes=colonnes, sequences=Sequence.objects.filter(actif=True),
    ))


@login_required
def compte_nouveau(request):
    if request.method == "POST":
        nom = request.POST.get("nom", "").strip()
        if not nom:
            messages.error(request, "Indiquez au moins la raison sociale.")
        else:
            c = Compte.objects.create(
                nom=nom, siren=re.sub(r"\D", "", request.POST.get("siren", ""))[:9], code_postal=request.POST.get("code_postal", "")[:5],
                ville=request.POST.get("ville", ""), effectif=int(request.POST.get("effectif") or 20),
                segment=request.POST.get("segment", "autre"), source=request.POST.get("source", "") or "Saisie manuelle", responsable=request.user,
            )
            Activite.objects.create(compte=c, type="systeme", texte="Prospect créé à la main.", utilisateur=request.user)
            recalculer(c)
            if request.POST.get("sirene"):
                ok, msg = sirene.rapprocher(c, request.user)
                (messages.success if ok else messages.warning)(request, msg)
            return redirect("prospection:compte", pk=c.pk)
    return render(request, "prospection/compte_nouveau.html", _ctx(request, segments=regles.SEGMENT_CHOICES))


@login_required
def compte(request, pk):
    c = get_object_or_404(Compte.objects.prefetch_related("signaux", "contacts", "activites"), pk=pk)
    canal = request.GET.get("canal", "email")
    canal = canal if canal in dict(redaction.CANAUX) else "email"
    ton = request.GET.get("ton", "direct")
    consigne = request.GET.get("consigne", "")
    contacts = c.contacts_actifs()
    try:
        contact = next(x for x in contacts if str(x.pk) == request.GET.get("contact")) if request.GET.get("contact") else c.contact_principal()
    except StopIteration:
        contact = c.contact_principal()
    message, erreur_ia = None, ""
    if request.GET.get("ia") and redaction.ia_disponible():
        try:
            message = redaction.rediger_ia(c, contact, canal, ton, consigne, utilisateur=request.user)
        except redaction.BudgetIAAtteint as e:
            erreur_ia = f"{e} Texte proposé par le modèle intégré."
        except Exception as e:  # IA indisponible : on garde le modèle intégré
            erreur_ia = f"L'IA n'a pas répondu ({e.__class__.__name__}). Texte proposé par le modèle intégré."
    message = message or redaction.generer(c, contact, canal, ton, consigne)
    controle = qualite.controler(message["texte"], canal, c)
    ids = [x.pk for x in _filtrer(request)[0]] if request.GET.get("liste") else list(Compte.objects.exclude(statut__in=["Écarté", "Opposé"]).order_by("-score", "nom").values_list("pk", flat=True))
    i = ids.index(c.pk) if c.pk in ids else -1
    ctx = _ctx(
        request, c=c, b=besoin(c), canal=canal, canaux=redaction.CANAUX, ton=ton, tons=redaction.TONS, consigne=consigne,
        contacts=contacts, contact=contact, message=message, controle=controle, erreur_ia=erreur_ia, ia_dispo=redaction.ia_disponible(),
        brief=redaction.brief(c), statuts=regles.STATUTS, segments=regles.SEGMENT_CHOICES, types_signaux=regles.SIGNAL_CHOICES,
        roles=regles.ROLES, statuts_email=regles.STATUTS_EMAIL, precedent=ids[i - 1] if i > 0 else None,
        suivant=ids[i + 1] if 0 <= i < len(ids) - 1 else None, position=i + 1, total=len(ids),
        oppose_email=bool(contact and contact.email and rgpd.est_oppose(contact.email)),
    )
    from .models import Inscription, Sequence
    ctx["sequences_dispo"] = Sequence.objects.filter(actif=True)
    ctx["inscription_en_cours"] = Inscription.objects.filter(contact__compte=c, statut__in=["active", "pause"]).select_related("sequence", "contact").first()
    g = c.signal_principal()
    ctx["controle_info"] = {
        "canal": canal, "noms": [c.nom] + [x.nom_complet for x in c.contacts.all()],
        "motif": qualite.MOTS_SIGNAL.get(g.type, "") if g else "", "signal": regles.SIGNAUX[g.type]["libelle"].lower() if g else "",
    }
    if ctx["linkedin_actif"]:
        ctx["li"] = {
            "compteurs": linkedin.compteurs(request.user),
            "connexion": ConnexionLinkedIn.objects.filter(utilisateur=request.user).first(),
            "recherche_entreprise": linkedin.recherche_entreprise(c.nom), "recherche_decideur": linkedin.recherche_decideur(c.nom),
            "recherche_contact": linkedin.recherche_personne(contact.prenom, contact.nom, c.nom) if contact else "",
            "invitation": redaction.generer(c, contact, "linkedin")["texte"],
            "actions": ActionLinkedIn.objects.filter(compte=c)[:5],
        }
    return render(request, "prospection/compte.html", ctx)


@login_required
@require_POST
def compte_action(request, pk):
    c = get_object_or_404(Compte, pk=pk)
    a = request.POST.get("action")
    u = request.user
    retour = _retour_sur(request, reverse("prospection:compte", args=[c.pk]))
    if a == "statut":
        c.statut = request.POST.get("statut", c.statut)
        if c.statut == "Pas maintenant" and request.POST.get("date_reprise"):
            c.date_reprise = request.POST["date_reprise"]
        c.save()
        Activite.objects.create(compte=c, type="statut", texte=f"Statut → {c.statut}", utilisateur=u)
        messages.success(request, f"Statut : {c.statut}.")
    elif a == "modifier":
        for champ in ("siren", "code_postal", "ville", "naf", "opco", "site_web", "linkedin_url"):
            if champ in request.POST:
                setattr(c, champ, request.POST[champ].strip())
        c.siren = re.sub(r"\D", "", c.siren)[:9]
        c.departement = c.code_postal[:2] if c.code_postal else c.departement
        for champ in ("effectif", "nb_etablissements"):
            if request.POST.get(champ, "").isdigit():
                setattr(c, champ, int(request.POST[champ]))
        c.segment = request.POST.get("segment", c.segment)
        c.icpe, c.erp, c.est_client = bool(request.POST.get("icpe")), bool(request.POST.get("erp")), bool(request.POST.get("est_client"))
        c.save()
        recalculer(c)
        messages.success(request, "Fiche enregistrée, score recalculé.")
    elif a == "sirene":
        ok, msg = sirene.rapprocher(c, u)
        (messages.success if ok else messages.warning)(request, msg)
    elif a == "contact":
        nom = request.POST.get("nom", "").strip()
        if not nom:
            messages.error(request, "Indiquez le nom du contact.")
        else:
            email = request.POST.get("email", "").strip().lower()
            if email and rgpd.est_oppose(email):
                messages.error(request, "Cette adresse est sur la liste d'opposition : contact non ajouté.")
            else:
                Contact.objects.create(
                    compte=c, prenom=request.POST.get("prenom", "").strip(), nom=nom, fonction=request.POST.get("fonction", "").strip(),
                    role=request.POST.get("role", "utilisateur"), email=email, statut_email=request.POST.get("statut_email", "probable" if email else "absent"),
                    telephone=request.POST.get("telephone", "").strip(), linkedin_url=request.POST.get("linkedin_url", "").strip(),
                )
                Activite.objects.create(compte=c, type="systeme", texte=f"Contact ajouté : {nom}.", utilisateur=u)
                recalculer(c)
                messages.success(request, "Contact ajouté.")
    elif a == "contact_supprimer":
        Contact.objects.filter(compte=c, pk=request.POST.get("contact_id")).delete()
        recalculer(c)
    elif a == "signal":
        type_ = request.POST.get("type")
        if type_ in regles.SIGNAUX and request.POST.get("texte"):
            Signal.objects.create(compte=c, type=type_, texte=request.POST["texte"][:300], source=request.POST.get("source", "") or "Saisie",
                                  url=request.POST.get("url", ""), date_signal=request.POST.get("date_signal") or timezone.localdate())
            recalculer(c)
            messages.success(request, "Signal ajouté, score recalculé.")
    elif a == "signal_off":
        Signal.objects.filter(compte=c, pk=request.POST.get("signal_id")).update(actif=False)
        recalculer(c)
    elif a == "tache":
        Tache.objects.create(compte=c, type=request.POST.get("type", "appel"), titre=request.POST.get("titre") or f"Appeler {c.contact_principal() or c.nom}",
                             echeance=request.POST.get("echeance") or timezone.localdate() + timedelta(days=1), assignee=u, origine="Fiche")
        messages.success(request, "Tâche créée.")
    elif a == "note":
        if request.POST.get("texte"):
            Activite.objects.create(compte=c, type=request.POST.get("type", "note"), texte=request.POST["texte"], utilisateur=u)
    elif a == "envoye":
        contact = Contact.objects.filter(compte=c, pk=request.POST.get("contact_id")).first()
        canal = request.POST.get("canal", "email")
        if contact and contact.email and rgpd.est_oppose(contact.email):
            messages.error(request, "Envoi bloqué : adresse sur la liste d'opposition.")
        else:
            if contact and not contact.informe_le and canal in ("email", "relance"):
                contact.informe_le = timezone.now()
                contact.save(update_fields=["informe_le"])
            Activite.objects.create(compte=c, contact=contact, type="email" if canal in ("email", "relance") else canal,
                                    texte=f"{dict(redaction.CANAUX).get(canal, canal)} envoyé : {request.POST.get('objet', '')}\n\n{request.POST.get('texte', '')[:3000]}", utilisateur=u)
            if c.statut in ("Nouveau", "À qualifier", "À contacter"):
                c.statut = "En contact"
                c.save(update_fields=["statut"])
            if request.POST.get("relance"):
                Tache.objects.create(compte=c, contact=contact, type="appel", titre=f"Relancer {contact or c.nom} (sans réponse)",
                                     echeance=timezone.localdate() + timedelta(days=int(request.POST.get("relance") or 5)), assignee=u, origine="Suite à l'envoi")
            messages.success(request, "Envoi noté dans l'historique." + (" Relance planifiée." if request.POST.get("relance") else ""))
    elif a == "decouverte":
        c.decouverte = {k: request.POST.get(k, "") for k in ("sst", "exercice", "decideur", "prestataire", "financement", "echeance")}
        c.save(update_fields=["decouverte"])
        Activite.objects.create(compte=c, type="appel", texte="Découverte : " + " · ".join(f"{k} : {v}" for k, v in c.decouverte.items() if v), utilisateur=u)
        messages.success(request, "Réponses de découverte enregistrées.")
    elif a == "ecarter":
        c.statut = "Écarté"
        c.save(update_fields=["statut"])
        Activite.objects.create(compte=c, type="statut", texte=f"Écarté : {request.POST.get('motif', '')}", utilisateur=u)
        messages.success(request, "Prospect écarté.")
    elif a == "opposer":
        rgpd.opposer_compte(c, u)
        messages.success(request, "Opposition enregistrée : plus aucun envoi vers ce prospect.")
    elif a == "linkedin":
        if not Parametres.get().linkedin_actif:
            raise Http404
        type_ = request.POST.get("type")
        contact = Contact.objects.filter(compte=c, pk=request.POST.get("contact_id")).first()
        if type_ in dict(ActionLinkedIn.TYPES):
            ActionLinkedIn.objects.create(utilisateur=u, compte=c, contact=contact, type=type_)
            Activite.objects.create(compte=c, contact=contact, type="linkedin", texte=f"LinkedIn : {dict(ActionLinkedIn.TYPES)[type_].lower()}"
                                    + (f" ({contact})" if contact else "") + ".", utilisateur=u)
            if type_ != "profil" and c.statut in ("Nouveau", "À qualifier", "À contacter"):
                c.statut = "En contact"
                c.save(update_fields=["statut"])
            cpt = linkedin.compteurs(u)
            if cpt["invitations_atteint"] or cpt["profils_atteint"]:
                messages.warning(request, "Plafond LinkedIn atteint : arrêtez pour aujourd'hui afin de protéger votre compte.")
            else:
                messages.success(request, "Action LinkedIn notée.")
    elif a == "contact_linkedin":
        Contact.objects.filter(compte=c, pk=request.POST.get("contact_id")).update(linkedin_url=request.POST.get("linkedin_url", "").strip())
        messages.success(request, "Profil LinkedIn enregistré.")
    return HttpResponseRedirect(retour)


# ------------------------------------------------------------------ Import


@login_required
def import_fichier(request):
    if request.method == "POST" and request.FILES.get("fichier"):
        f = request.FILES["fichier"]
        type_ = request.POST.get("type", "prospects")
        try:
            entetes, lignes = imports.lire_fichier(f.name, f.read())
        except Exception as e:
            messages.error(request, f"Fichier illisible : {e}")
            return redirect("prospection:import")
        if not entetes:
            messages.error(request, "Le fichier est vide.")
            return redirect("prospection:import")
        imp = ImportFichier.objects.create(nom_fichier=f.name, type=type_, entetes=entetes, lignes=lignes[:5000],
                                           correspondance=imports.deviner_correspondance(entetes, type_), importe_par=request.user)
        return redirect("prospection:import_detail", pk=imp.pk)
    return render(request, "prospection/import.html", _ctx(request, imports_recents=ImportFichier.objects.all()[:10], formao_configuree=formao.configuree()))


@login_required
def import_detail(request, pk):
    imp = get_object_or_404(ImportFichier, pk=pk)
    champs = imports.CHAMPS_PROSPECTS if imp.type == "prospects" else imports.CHAMPS_HISTORIQUE
    if request.method == "POST" and not imp.applique_le:
        imp.correspondance = [request.POST.get(f"col{i}", "") for i in range(len(imp.entetes))]
        imp.save(update_fields=["correspondance"])
        if request.POST.get("appliquer"):
            if imp.type == "prospects":
                r = imports.appliquer(imp, request.user)
                messages.success(request, f"{r['crees']} prospects créés, {r['completes']} fiches existantes complétées.")
                return redirect(reverse("prospection:prospects") + "?vue=tous")
            r = imports.appliquer_historique(imp)
            messages.success(request, f"{r['crees']} formations enregistrées" + (f", {len(r['rejets'])} lignes rejetées (date ou prestation illisible)." if r["rejets"] else "."))
            return redirect("prospection:historique")
    analyse = imports.analyser(imp) if imp.type == "prospects" else []
    cpt = {}
    for x in analyse:
        cpt[x["etat"]] = cpt.get(x["etat"], 0) + 1
    exemple = imp.lignes[0] if imp.lignes else []
    colonnes = [(i, h, imp.correspondance[i] if i < len(imp.correspondance) else "", exemple[i] if i < len(exemple) else "") for i, h in enumerate(imp.entetes)]
    a_importer = sum(1 for x in analyse if x["etat"] in ("Nouveau", "À vérifier")) if imp.type == "prospects" else len(imp.lignes)
    return render(request, "prospection/import_detail.html", _ctx(
        request, imp=imp, champs=champs.items(), colonnes=colonnes, analyse=analyse[:300], compteurs=cpt, a_importer=a_importer,
        nb_completes=sum(1 for x in analyse if x["doublon_id"]), nb_verifier=cpt.get("À vérifier", 0),
        nb_opposes=cpt.get("Opposé", 0), nb_rejetes=cpt.get("Rejeté", 0),
    ))


@login_required
@require_POST
def import_annuler(request, pk):
    imp = get_object_or_404(ImportFichier, pk=pk)
    if imp.annulable:
        n = imports.annuler(imp)
        messages.success(request, f"Import annulé : {n} prospects supprimés.")
    return redirect("prospection:import")


@login_required
@require_POST
def acheteurs_ao(request):
    """Acheteurs publics lus dans FORM'AO (connexion facultative) : un prospect par acheteur, un signal par avis."""
    try:
        liste = formao.acheteurs()
    except formao.FormaoIndisponible as e:
        messages.error(request, str(e))
        return redirect("prospection:import")
    crees = signaux = 0
    for a in liste[:1000]:
        nom = (a.get("nom") or "").strip()
        if not nom:
            continue
        siren = re.sub(r"\D", "", a.get("siren") or "")[:9]
        n = re.sub(r"[^a-z0-9]+", " ", normaliser(nom)).strip()
        c = (Compte.objects.filter(siren=siren).first() if siren else None) or Compte.objects.filter(nom_normalise=n).first()
        if not c:
            c = Compte.objects.create(nom=nom, siren=siren, segment="collectivite", effectif=100, source="FORM'AO (acheteur public)",
                                      departement=(a.get("departement") or "")[:3], statut="Nouveau")
            crees += 1
        for avis in a.get("avis", [])[:20]:
            objet = (avis.get("objet") or "")[:120]
            if objet and not c.signaux.filter(type="ao", texte=f"Avis « {objet} »").exists():
                Signal.objects.create(compte=c, type="ao", texte=f"Avis « {objet} »", source="FORM'AO", url=avis.get("url") or "",
                                      date_signal=avis.get("date_publication") or timezone.localdate())
                signaux += 1
        recalculer(c)
    messages.success(request, f"FORM'AO : {crees} acheteurs publics ajoutés, {signaux} signaux.")
    return redirect(reverse("prospection:prospects") + "?vue=public")


@login_required
@require_POST
def formao_synchroniser(request):
    if not request.user.is_staff:
        raise Http404
    try:
        crees, maj = formao.synchroniser_profil_et_catalogue()
        n = recalculer_tout()
        messages.success(request, f"Profil et catalogue repris de FORM'AO ({crees} prestations ajoutées, {maj} mises à jour). {n} scores recalculés.")
    except formao.FormaoIndisponible as e:
        messages.error(request, str(e))
    return redirect("prospection:import")


# ------------------------------------------------------------------ Historique


@login_required
def historique(request):
    if request.method == "POST":
        nom = request.POST.get("nom_client", "").strip()
        pr = request.POST.get("prestation")
        if nom and pr in regles.ECHEANCES and request.POST.get("date_session"):
            n = re.sub(r"[^a-z0-9]+", " ", normaliser(nom)).strip()
            HistoriqueFormation.objects.create(
                compte=Compte.objects.filter(nom_normalise=n).first(), nom_client=nom, prestation=pr, date_session=request.POST["date_session"],
                nb_stagiaires=int(request.POST.get("nb_stagiaires") or 1), formateur=request.POST.get("formateur", ""), source="saisie",
            )
            messages.success(request, "Session enregistrée, échéance calculée.")
        else:
            messages.error(request, "Indiquez le client, la prestation et la date.")
        return redirect("prospection:historique")
    lignes = sorted(HistoriqueFormation.objects.select_related("compte"), key=lambda h: h.jours_restants)
    clients = sorted(set(HistoriqueFormation.objects.values_list("nom_client", flat=True)) | set(Compte.objects.filter(est_client=True).values_list("nom", flat=True)))
    return render(request, "prospection/historique.html", _ctx(
        request, lignes=lignes, prestations=regles.ECHEANCES.items(), clients=clients,
        nb_retard=sum(1 for h in lignes if h.etat == "retard"), nb_relancer=sum(1 for h in lignes if h.etat == "relancer"),
        stagiaires_12=sum(h.nb_stagiaires for h in lignes if h.jours_restants <= 365 and "SST" in h.prestation),
    ))


def creer_relance(h: HistoriqueFormation, utilisateur=None) -> None:
    Tache.objects.create(compte=h.compte, type="appel", titre=f"Relance {h.prestation} : {h.nom_client} ({h.nb_stagiaires} stagiaire{'s' if h.nb_stagiaires > 1 else ''}, échéance {h.echeance:%d/%m/%Y})",
                         echeance=timezone.localdate(), assignee=utilisateur, origine="Historique des formations")
    if h.compte and "SST" in h.prestation:
        Signal.objects.get_or_create(compte=h.compte, type="mac", texte=f"MAC SST de {h.nb_stagiaires} salariés à prévoir avant le {h.echeance:%d/%m/%Y}",
                                     defaults={"source": "Historique des formations", "date_signal": timezone.localdate()})
        recalculer(h.compte)
    h.relance_creee = True
    h.save(update_fields=["relance_creee"])


@login_required
@require_POST
def historique_relancer(request):
    if request.POST.get("id"):
        qs = HistoriqueFormation.objects.filter(pk=request.POST["id"])
    else:
        qs = HistoriqueFormation.objects.filter(relance_creee=False)
    n = 0
    for h in qs:
        if h.etat != "ok" and not h.relance_creee:
            creer_relance(h, request.user)
            n += 1
    if request.POST.get("cle"):
        ReportAction.objects.update_or_create(utilisateur=request.user, cle=request.POST["cle"], jour=timezone.localdate(), defaults={"faite": True})
    messages.success(request, f"{n} relance{'s' if n > 1 else ''} créée{'s' if n > 1 else ''} dans les tâches.")
    return redirect(_retour_sur(request, reverse("prospection:historique")))


# ------------------------------------------------------------------ Tâches


@login_required
def taches(request):
    if request.method == "POST":
        t = get_object_or_404(Tache, pk=request.POST.get("id"))
        if request.POST.get("quoi") == "fait":
            t.faite_le = None if t.faite_le else timezone.now()
        elif request.POST.get("quoi") == "reporter":
            t.echeance = timezone.localdate() + timedelta(days=int(request.POST.get("jours") or 1))
        t.save()
        return redirect(request.get_full_path())
    type_ = request.GET.get("type", "")
    qs = Tache.objects.select_related("compte").filter(Q(faite_le__isnull=True) | Q(faite_le__gte=timezone.now() - timedelta(days=1)))
    if type_:
        qs = qs.filter(type=type_)
    return render(request, "prospection/taches.html", _ctx(request, taches=qs.order_by("faite_le", "echeance")[:300], type=type_, types=Tache.TYPES))


# ------------------------------------------------------------------ Opposition


@login_required
def oppositions(request):
    if request.method == "POST":
        if request.POST.get("supprimer"):
            Opposition.objects.filter(pk=request.POST["supprimer"]).delete()
            messages.success(request, "Retiré de la liste d'opposition.")
        else:
            v = request.POST.get("valeur", "").strip().lower()
            if not re.fullmatch(r"(@[\w.-]+\.\w+|[\w.+-]+@[\w.-]+\.\w+)", v):
                messages.error(request, "Saisissez une adresse e-mail ou un domaine commençant par @.")
            else:
                n = rgpd.enregistrer_opposition(v, source="Saisie", utilisateur=request.user)
                messages.success(request, "Opposition ajoutée" + (f" : {n} contact{'s' if n > 1 else ''} bloqué{'s' if n > 1 else ''}." if n else "."))
        return redirect("prospection:oppositions")
    return render(request, "prospection/oppositions.html", _ctx(request, liste=Opposition.objects.all()[:500]))


# ------------------------------------------------------------------ LinkedIn (option)


def _option_linkedin():
    if not Parametres.get().linkedin_actif:
        raise Http404("Option LinkedIn désactivée")


@login_required
def linkedin_page(request):
    _option_linkedin()
    return render(request, "prospection/linkedin.html", _ctx(
        request, configuree=linkedin.configuree(), connexion=ConnexionLinkedIn.objects.filter(utilisateur=request.user).first(),
        url_retour=linkedin.url_retour(), compteurs=linkedin.compteurs(request.user), posts=linkedin.POSTS_PROPOSES,
        publications=PublicationLinkedIn.objects.filter(utilisateur=request.user)[:10], consignes=linkedin.CONSIGNES_COPILOTE,
        actions=ActionLinkedIn.objects.filter(utilisateur=request.user).select_related("compte")[:15],
    ))


@login_required
def linkedin_connecter(request):
    _option_linkedin()
    if not linkedin.configuree():
        messages.error(request, "Renseignez LINKEDIN_CLIENT_ID et LINKEDIN_CLIENT_SECRET dans le fichier .env du serveur.")
        return redirect("prospection:linkedin")
    return HttpResponseRedirect(linkedin.url_autorisation(request.session))


@login_required
def linkedin_retour(request):
    _option_linkedin()
    if request.GET.get("error"):
        messages.warning(request, f"Connexion annulée sur LinkedIn : {request.GET.get('error_description', request.GET['error'])}.")
        return redirect("prospection:linkedin")
    try:
        cx = linkedin.terminer_connexion(request.user, request.GET.get("code", ""), request.GET.get("state", ""), request.session)
        messages.success(request, f"Compte LinkedIn connecté : {cx.nom}. Valable jusqu'au {timezone.localtime(cx.expire_le):%d/%m/%Y}.")
    except linkedin.ErreurLinkedIn as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f"LinkedIn ne répond pas ({e.__class__.__name__}). Réessayez.")
    return redirect("prospection:linkedin")


@login_required
@require_POST
def linkedin_deconnecter(request):
    _option_linkedin()
    ConnexionLinkedIn.objects.filter(utilisateur=request.user).delete()
    messages.success(request, "Compte LinkedIn déconnecté de l'agent. Vous pouvez aussi retirer l'accès depuis LinkedIn (Préférences > Données).")
    return redirect("prospection:linkedin")


@login_required
@require_POST
def linkedin_publier(request):
    _option_linkedin()
    texte = request.POST.get("texte", "").strip()
    if not texte:
        messages.error(request, "Le texte du post est vide.")
        return redirect("prospection:linkedin")
    if len(texte) > 3000:
        messages.error(request, "Un post LinkedIn fait au plus 3 000 caractères.")
        return redirect("prospection:linkedin")
    pub = PublicationLinkedIn.objects.create(utilisateur=request.user, texte=texte)
    if request.POST.get("quoi") == "brouillon":
        messages.success(request, "Brouillon enregistré.")
        return redirect("prospection:linkedin")
    try:
        linkedin.publier(pub)
        messages.success(request, "Post publié sur votre profil LinkedIn.")
    except linkedin.ErreurLinkedIn as e:
        messages.error(request, str(e))
    except Exception as e:
        pub.statut, pub.erreur = "erreur", str(e)
        pub.save()
        messages.error(request, f"LinkedIn ne répond pas ({e.__class__.__name__}). Le post est gardé en erreur, réessayez.")
    return redirect("prospection:linkedin")


@login_required
@require_POST
def linkedin_republier(request, pk):
    _option_linkedin()
    pub = get_object_or_404(PublicationLinkedIn, pk=pk, utilisateur=request.user)
    try:
        linkedin.publier(pub)
        messages.success(request, "Post publié sur votre profil LinkedIn.")
    except Exception as e:
        messages.error(request, str(e))
    return redirect("prospection:linkedin")
