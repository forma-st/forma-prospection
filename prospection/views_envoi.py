"""Écrans de la phase 2 : séquences, messagerie, réponses, statistiques."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import regles
from .models import (Activite, BoiteEnvoi, Compte, Contact, EtapeSequence, Inscription, Message, Parametres, Sequence, Tache)
from .services import messagerie, qualite, sequences as svc_seq
from .services.reponses import appliquer as appliquer_reponse
from .views import _ctx, _retour_sur


def _staff(request):
    if not request.user.is_staff:
        raise Http404


# ------------------------------------------------------------------ Séquences


@login_required
def sequences(request):
    if request.method == "POST":
        _staff(request)
        nom = request.POST.get("nom", "").strip()
        if nom:
            s = Sequence.objects.create(nom=nom, mode_validation="premier")
            EtapeSequence.objects.create(sequence=s, ordre=1, type="email")
            return redirect("prospection:sequence", pk=s.pk)
    liste = Sequence.objects.annotate(
        nb_actives=Count("inscriptions", filter=Q(inscriptions__statut="active")),
        nb_total=Count("inscriptions", distinct=True),
    ).prefetch_related("etapes")
    stats = {}
    for s in liste:
        env = Message.objects.filter(inscription__sequence=s, sens="sortant", statut="envoye").count()
        rep = Message.objects.filter(sens="entrant", contact__inscriptions__sequence=s).exclude(classe__in=["absence", "rebond"]).values("contact").distinct().count()
        stats[s.pk] = {"envoyes": env, "reponses": rep, "taux": round(rep / s.nb_total * 100) if s.nb_total else 0}
    return render(request, "prospection/sequences.html", _ctx(request, liste=liste, stats=stats))


@login_required
def sequence(request, pk):
    s = get_object_or_404(Sequence, pk=pk)
    if request.method == "POST":
        _staff(request)
        a = request.POST.get("action")
        if a == "reglages":
            s.nom = request.POST.get("nom", s.nom).strip() or s.nom
            s.description = request.POST.get("description", "")
            s.mode_validation = request.POST.get("mode_validation", s.mode_validation)
            s.actif = bool(request.POST.get("actif"))
            s.save()
        elif a == "ajouter":
            dernier = s.etapes.order_by("-ordre").first()
            EtapeSequence.objects.create(sequence=s, ordre=(dernier.ordre + 1) if dernier else 1, type=request.POST.get("type", "email"),
                                         delai_jours=int(request.POST.get("delai_jours") or 3), canal_redaction="relance" if dernier else "email",
                                         intitule=request.POST.get("intitule", ""))
        elif a == "etape":
            e = get_object_or_404(EtapeSequence, pk=request.POST.get("etape_id"), sequence=s)
            for champ in ("type", "canal_redaction", "objet", "corps", "intitule"):
                if champ in request.POST:
                    setattr(e, champ, request.POST[champ])
            e.delai_jours = int(request.POST.get("delai_jours") or 0)
            e.save()
        elif a == "supprimer":
            s.etapes.filter(pk=request.POST.get("etape_id")).delete()
            for i, e in enumerate(s.etapes.order_by("ordre"), start=1):
                EtapeSequence.objects.filter(pk=e.pk).update(ordre=i)
        elif a in ("monter", "descendre"):
            etapes = list(s.etapes.order_by("ordre"))
            i = next((n for n, e in enumerate(etapes) if str(e.pk) == request.POST.get("etape_id")), None)
            j = (i - 1) if a == "monter" else (i + 1) if i is not None else None
            if i is not None and 0 <= j < len(etapes):
                etapes[i], etapes[j] = etapes[j], etapes[i]
                for n, e in enumerate(etapes, start=1):
                    EtapeSequence.objects.filter(pk=e.pk).update(ordre=n)
        messages.success(request, "Séquence enregistrée.")
        return redirect("prospection:sequence", pk=s.pk)
    inscriptions = s.inscriptions.select_related("contact__compte").order_by("statut", "prochaine_le")[:200]
    return render(request, "prospection/sequence.html", _ctx(
        request, s=s, etapes=s.etapes.order_by("ordre"), inscriptions=inscriptions, types=EtapeSequence.TYPES, modes=Sequence.MODES))


@login_required
@require_POST
def inscrire(request):
    s = get_object_or_404(Sequence, pk=request.POST.get("sequence"), actif=True)
    ids = request.POST.getlist("contact") or []
    comptes = request.POST.getlist("compte") or []
    contacts = list(Contact.objects.filter(pk__in=ids)) + [c.contact_principal() for c in Compte.objects.filter(pk__in=comptes) if c.contact_principal()]
    ok, refus = 0, []
    for k in contacts:
        try:
            svc_seq.inscrire(s, k, request.user)
            ok += 1
        except svc_seq.InscriptionImpossible as e:
            refus.append(str(e))
    if ok:
        messages.success(request, f"{ok} contact{'s' if ok > 1 else ''} inscrit{'s' if ok > 1 else ''} dans « {s.nom} ». Le premier e-mail sera préparé au prochain passage (5 min au plus).")
    for r in refus[:5]:
        messages.warning(request, r)
    return redirect(_retour_sur(request, reverse("prospection:sequence", args=[s.pk])))


@login_required
@require_POST
def desinscrire(request, pk):
    ins = get_object_or_404(Inscription, pk=pk)
    svc_seq.arreter(ins.contact, "Arrêtée à la main")
    messages.success(request, "Séquence arrêtée pour ce contact.")
    return redirect(_retour_sur(request, reverse("prospection:sequence", args=[ins.sequence_id])))


# ------------------------------------------------------------------ Messagerie


CHAMPS_BOITE = ["nom", "adresse", "nom_affiche", "smtp_hote", "smtp_port", "smtp_securite", "smtp_identifiant", "imap_hote", "imap_port",
                "imap_identifiant", "plafond_jour", "signature"]


@login_required
def messagerie_page(request):
    p = Parametres.get()
    if request.method == "POST":
        a = request.POST.get("action")
        if a == "parametres":
            _staff(request)
            p.mode_test = bool(request.POST.get("mode_test"))
            p.adresse_test = request.POST.get("adresse_test", "").strip()
            p.plages_envoi = request.POST.get("plages_envoi", p.plages_envoi).strip() or p.plages_envoi
            if not p.mode_test and not BoiteEnvoi.objects.filter(actif=True).exists():
                messages.error(request, "Ajoutez d'abord une boîte d'envoi.")
                p.mode_test = True
            p.save()
            messages.success(request, "Mode test activé : aucun prospect ne reçoit rien." if p.mode_test else "Mode test désactivé : les e-mails partent réellement aux prospects.")
        elif a == "boite":
            _staff(request)
            b = BoiteEnvoi.objects.filter(pk=request.POST.get("boite_id")).first() or BoiteEnvoi(utilisateur=request.user)
            for champ in CHAMPS_BOITE:
                if champ in request.POST:
                    v = request.POST[champ].strip()
                    setattr(b, champ, int(v) if champ in ("smtp_port", "imap_port", "plafond_jour") and v.isdigit() else v)
            for champ in ("smtp_mot_de_passe", "imap_mot_de_passe"):
                if request.POST.get(champ):
                    setattr(b, champ, request.POST[champ])
            b.actif = bool(request.POST.get("actif", "1"))
            if not (b.adresse and b.smtp_hote):
                messages.error(request, "Adresse et serveur SMTP obligatoires.")
            else:
                b.save()
                messages.success(request, f"Boîte {b.adresse} enregistrée. Testez la connexion.")
        elif a == "tester":
            b = get_object_or_404(BoiteEnvoi, pk=request.POST.get("boite_id"))
            messages.info(request, messagerie.tester_boite(b))
        elif a in ("valider", "annuler", "envoyer"):
            m = get_object_or_404(Message, pk=request.POST.get("message_id"), sens="sortant")
            if a == "annuler":
                m.statut = "annule"
                m.save(update_fields=["statut"])
                messages.success(request, "Message annulé.")
            else:
                if request.POST.get("objet"):
                    m.objet = request.POST["objet"]
                if request.POST.get("corps"):
                    m.corps = request.POST["corps"]
                messagerie.programmer(m, request.user)
                if a == "envoyer":
                    try:
                        messagerie.envoyer(m)
                        messages.success(request, "Message envoyé" + (" (mode test : vers l'adresse de test)." if p.mode_test else "."))
                    except messagerie.EnvoiImpossible as e:
                        messages.error(request, str(e))
                else:
                    messages.success(request, f"Message programmé pour le {timezone.localtime(m.prevu_le):%d/%m à %H h %M}.")
        elif a == "file":
            r = messagerie.traiter_file()
            messages.info(request, "Hors plage d'envoi : les messages partiront au prochain créneau." if r["hors_plage"] else f"{r['envoyes']} message(s) envoyé(s), {r['erreurs']} refusé(s).")
        return redirect(request.path + (f"?onglet={request.POST.get('onglet')}" if request.POST.get("onglet") else ""))
    onglet = request.GET.get("onglet", "a_valider")
    filtres = {"a_valider": ["a_valider"], "programmes": ["programme", "envoi"], "envoyes": ["envoye"], "erreurs": ["erreur", "annule"]}
    file = Message.objects.filter(sens="sortant", statut__in=filtres.get(onglet, ["a_valider"])).select_related("compte", "contact", "boite").order_by("-cree_le")[:200]
    compteurs = {k: Message.objects.filter(sens="sortant", statut__in=v).count() for k, v in filtres.items()}
    boites = BoiteEnvoi.objects.all()
    return render(request, "prospection/messagerie.html", _ctx(
        request, p=p, boites=boites, file=file, onglet=onglet, compteurs=compteurs,
        boite_edit=BoiteEnvoi.objects.filter(pk=request.GET.get("boite")).first(), dans_plage=messagerie.dans_les_plages(timezone.now(), p),
        prochain=messagerie.prochain_creneau(timezone.now(), p), securites=BoiteEnvoi._meta.get_field("smtp_securite").choices,
    ))


@login_required
@require_POST
def envoyer_depuis_fiche(request, pk):
    c = get_object_or_404(Compte, pk=pk)
    k = get_object_or_404(Contact, pk=request.POST.get("contact_id"), compte=c)
    boite = messagerie.boite_par_defaut(request.user)
    if not boite:
        messages.error(request, "Aucune boîte d'envoi : ajoutez-en une dans Messagerie (ou utilisez « Ouvrir dans ma messagerie »).")
    elif not k.email:
        messages.error(request, "Ce contact n'a pas d'adresse e-mail.")
    else:
        corps = messagerie.appliquer_signature(request.POST.get("texte", ""), boite)
        m = Message.objects.create(compte=c, contact=k, boite=boite, destinataire=k.email, objet=request.POST.get("objet", "")[:255] or f"Formations sécurité – {c.nom}",
                                   corps=corps, note_qualite=(qualite.controler(corps, "email", c) or {}).get("note"))
        messagerie.programmer(m, request.user)
        if c.statut in ("Nouveau", "À qualifier", "À contacter"):
            c.statut = "En contact"
            c.save(update_fields=["statut"])
        if request.POST.get("relance"):
            Tache.objects.create(compte=c, contact=k, type="appel", titre=f"Relancer {k} (sans réponse)", assignee=request.user, origine="Suite à l'envoi",
                                 echeance=timezone.localdate() + timedelta(days=int(request.POST["relance"])))
        p = Parametres.get()
        messages.success(request, f"E-mail programmé pour le {timezone.localtime(m.prevu_le):%d/%m à %H h %M}" + (" (mode test : il partira vers l'adresse de test)." if p.mode_test else "."))
    return redirect(reverse("prospection:compte", args=[c.pk]))


# ------------------------------------------------------------------ Réponses


@login_required
def reponses_page(request):
    if request.method == "POST":
        r = get_object_or_404(Message, pk=request.POST.get("id"), sens="entrant")
        a = request.POST.get("action")
        if a == "classer" and request.POST.get("classe") in dict(Message.CLASSES):
            r.classe, r.confiance, r.traite = request.POST["classe"], 100, False
            r.save(update_fields=["classe", "confiance", "traite"])
            appliquer_reponse(r)
            messages.success(request, "Classement corrigé.")
        elif a == "reprise" and r.compte:
            c = r.compte
            c.statut, c.date_reprise = "Pas maintenant", request.POST.get("date_reprise") or (timezone.localdate() + timedelta(days=90))
            c.save(update_fields=["statut", "date_reprise"])
            r.traite = True
            r.save(update_fields=["traite"])
            messages.success(request, "Reprise planifiée : le prospect reviendra dans « Ma journée » à la date choisie.")
        elif a == "contact" and r.compte and request.POST.get("nom"):
            Contact.objects.create(compte=r.compte, prenom=request.POST.get("prenom", ""), nom=request.POST["nom"], fonction=request.POST.get("fonction", ""),
                                   email=request.POST.get("email", "").lower(), statut_email="probable" if request.POST.get("email") else "absent", role="decideur")
            Activite.objects.create(compte=r.compte, type="systeme", texte=f"Contact ajouté depuis la réponse de {r.contact} : {request.POST['nom']}.")
            r.traite = True
            r.save(update_fields=["traite"])
            messages.success(request, "Contact ajouté. Vous pouvez l'inscrire en séquence depuis la fiche.")
        elif a == "rdv" and r.compte:
            r.compte.statut = "RDV fixé"
            r.compte.save(update_fields=["statut"])
            r.traite = True
            r.save(update_fields=["traite"])
            Activite.objects.create(compte=r.compte, type="statut", texte="RDV fixé suite à la réponse.", utilisateur=request.user)
            messages.success(request, "RDV fixé.")
        elif a == "traite":
            r.traite = not r.traite
            r.save(update_fields=["traite"])
        return redirect(f"{request.path}?id={r.pk}")
    liste = Message.objects.filter(sens="entrant").select_related("compte", "contact").order_by("traite", "-cree_le")[:200]
    choisi = Message.objects.filter(pk=request.GET.get("id"), sens="entrant").first() or next(iter(liste), None)
    origine = Message.objects.filter(sens="sortant", message_id=choisi.en_reponse_a).first() if choisi and choisi.en_reponse_a else None
    return render(request, "prospection/reponses.html", _ctx(request, liste=liste, r=choisi, origine=origine, classes=Message.CLASSES))


# ------------------------------------------------------------------ Statistiques


@login_required
def statistiques(request):
    actifs = Compte.objects.exclude(statut__in=regles.STATUTS_INACTIFS)
    depuis = timezone.now() - timedelta(days=30)
    envoyes = Message.objects.filter(sens="sortant", statut="envoye", envoye_le__gte=depuis)
    recus = Message.objects.filter(sens="entrant", cree_le__gte=depuis).exclude(classe__in=["absence", "rebond"])
    entonnoir = [(s, Compte.objects.filter(statut=s).count()) for s in ["Nouveau", "À qualifier", "À contacter", "En contact", "A répondu", "RDV fixé", "Transmis au CRM", "Client"]]
    maxi = max([n for _, n in entonnoir] + [1])
    par_source = (Compte.objects.values("source").annotate(n=Count("id"), rdv=Count("id", filter=Q(statut__in=["RDV fixé", "Transmis au CRM", "Client"])),
                  rep=Count("id", filter=Q(statut__in=["A répondu", "RDV fixé", "Transmis au CRM", "Client"]))).order_by("-n")[:12])
    classes = recus.values("classe").annotate(n=Count("id")).order_by("-n")
    contactes = Compte.objects.filter(Q(messages__sens="sortant", messages__statut="envoye") | Q(activites__type__in=["email", "linkedin", "appel"])).distinct().count()
    repondu = Compte.objects.filter(statut__in=["A répondu", "RDV fixé", "Transmis au CRM", "Client"]).count()
    rdv = Compte.objects.filter(statut__in=["RDV fixé", "Transmis au CRM"]).count()
    return render(request, "prospection/statistiques.html", _ctx(
        request, nb_actifs=actifs.count(), nb_a=actifs.filter(palier="A").count(), envoyes=envoyes.count(), recus=recus.count(),
        rdv=rdv, entonnoir=[(s, n, round(n / maxi * 100)) for s, n in entonnoir], par_source=par_source,
        classes=[(dict(Message.CLASSES).get(x["classe"], x["classe"]), x["n"]) for x in classes],
        taux_reponse=round(repondu / contactes * 100) if contactes else 0, taux_rdv=round(rdv / repondu * 100) if repondu else 0,
        par_palier=[(p, actifs.filter(palier=p).count()) for p in "ABC"],
    ))
