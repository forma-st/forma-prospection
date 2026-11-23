"""Agent d'aide à la prospection : modèle de données (cahier des charges §5)."""

from __future__ import annotations

from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone

from . import regles


class Parametres(models.Model):
    """Réglages modifiables (un seul enregistrement)."""

    poids_adequation = models.PositiveSmallIntegerField(default=45)
    poids_intention = models.PositiveSmallIntegerField(default=35)
    poids_accessibilite = models.PositiveSmallIntegerField(default=20)
    seuil_palier_a = models.PositiveSmallIntegerField("Seuil du palier A", default=70)
    seuil_palier_b = models.PositiveSmallIntegerField("Seuil du palier B", default=50)
    part_sst = models.PositiveSmallIntegerField("Part de l'effectif à former SST (%)", default=12)
    departements_prioritaires = models.CharField(max_length=200, default="95,78,92,93,94,75,77,91,60")
    objectif_actions_jour = models.PositiveSmallIntegerField("Objectif d'actions par jour", default=8)

    linkedin_actif = models.BooleanField(
        "Activer l'option LinkedIn", default=False,
        help_text="Affiche le panneau LinkedIn sur les fiches et la page de connexion du compte.",
    )
    linkedin_invitations_semaine = models.PositiveSmallIntegerField("Invitations LinkedIn max. par semaine", default=50)
    linkedin_profils_jour = models.PositiveSmallIntegerField("Profils LinkedIn consultés max. par jour", default=30)

    mode_test = models.BooleanField(
        "Messagerie en mode test", default=True,
        help_text="Tous les e-mails partent vers l'adresse de test au lieu des prospects. À décocher pour envoyer pour de vrai.",
    )
    adresse_test = models.EmailField("Adresse de test", blank=True)
    plages_envoi = models.CharField("Plages d'envoi", max_length=60, default="08:30-11:30,14:00-17:00",
                                    help_text="Heures de Paris, jours ouvrés uniquement.")

    class Meta:
        verbose_name = "paramètres"
        verbose_name_plural = "paramètres"

    def __str__(self):
        return "Paramètres de la prospection"

    @classmethod
    def get(cls) -> "Parametres":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def departements(self) -> list[str]:
        return [d.strip() for d in self.departements_prioritaires.replace(";", ",").split(",") if d.strip()]


class ImportFichier(models.Model):
    TYPES = [("prospects", "Prospects"), ("historique", "Historique des formations")]
    nom_fichier = models.CharField(max_length=255)
    type = models.CharField(max_length=12, choices=TYPES, default="prospects")
    entetes = models.JSONField(default=list)
    lignes = models.JSONField(default=list)
    correspondance = models.JSONField(default=list)
    rapport = models.JSONField(default=dict, blank=True)
    applique_le = models.DateTimeField(null=True, blank=True)
    annule_le = models.DateTimeField(null=True, blank=True)
    importe_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "import de fichier"
        verbose_name_plural = "imports de fichiers"

    def __str__(self):
        return self.nom_fichier

    @property
    def annulable(self) -> bool:
        return bool(self.applique_le and not self.annule_le and (timezone.now() - self.applique_le).days < 30)


class Compte(models.Model):
    siren = models.CharField(max_length=9, blank=True, db_index=True)
    siret = models.CharField("SIRET (siège ou établissement visé)", max_length=14, blank=True)
    nom = models.CharField("Raison sociale", max_length=255)
    nom_normalise = models.CharField(max_length=255, db_index=True, editable=False)
    naf = models.CharField("Code NAF", max_length=6, blank=True)
    segment = models.CharField(max_length=20, choices=regles.SEGMENT_CHOICES, default="autre")
    effectif = models.PositiveIntegerField(default=20)
    nb_etablissements = models.PositiveIntegerField("Établissements", default=1)
    code_postal = models.CharField(max_length=5, blank=True)
    ville = models.CharField(max_length=120, blank=True)
    departement = models.CharField(max_length=3, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    site_web = models.URLField(blank=True)
    idcc = models.CharField("IDCC", max_length=20, blank=True)
    opco = models.CharField("OPCO", max_length=60, blank=True)
    icpe = models.BooleanField("Site ICPE", default=False)
    erp = models.BooleanField("Établissement recevant du public", default=False)
    est_client = models.BooleanField("Déjà client", default=False)
    linkedin_url = models.URLField("Page LinkedIn de l'entreprise", blank=True)

    statut = models.CharField(max_length=20, choices=regles.STATUT_CHOICES, default="Nouveau")
    date_reprise = models.DateField("Reprendre le", null=True, blank=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="comptes_prospection")
    source = models.CharField(max_length=120, blank=True)
    import_fichier = models.ForeignKey(ImportFichier, null=True, blank=True, on_delete=models.SET_NULL, related_name="comptes")
    notes = models.TextField(blank=True)

    score = models.PositiveSmallIntegerField(default=0)
    score_adequation = models.PositiveSmallIntegerField(default=0)
    score_intention = models.PositiveSmallIntegerField(default=0)
    score_accessibilite = models.PositiveSmallIntegerField(default=0)
    palier = models.CharField(max_length=1, default="C")
    explication = models.TextField(blank=True)
    decouverte = models.JSONField(default=dict, blank=True)

    sirene_le = models.DateTimeField("Rapproché avec l'annuaire le", null=True, blank=True)
    sirene_confiance = models.PositiveSmallIntegerField(null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score", "nom"]
        verbose_name = "compte prospect"

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        from .services.texte import normaliser
        import re
        n = normaliser(self.nom)
        n = re.sub(r"\b(sas|sarl|sa|sasu|eurl|sci|snc|et cie|cie)\b", " ", n)
        self.nom_normalise = re.sub(r"[^a-z0-9]+", " ", n).strip()
        if self.code_postal and not self.departement:
            self.departement = self.code_postal[:2]
        super().save(*args, **kwargs)

    @property
    def actif(self) -> bool:
        return self.statut not in regles.STATUTS_INACTIFS

    def contacts_actifs(self):
        return [c for c in self.contacts.all() if not c.oppose]

    def contact_principal(self):
        cs = self.contacts_actifs()
        return next((c for c in cs if c.role == "decideur"), None) or next((c for c in cs if c.role != "standard"), None) or (cs[0] if cs else None)

    def signal_principal(self):
        from .services.scoring import valeur_signal
        sigs = [s for s in self.signaux.all() if s.actif]
        return max(sigs, key=valeur_signal) if sigs else None


class Contact(models.Model):
    compte = models.ForeignKey(Compte, on_delete=models.CASCADE, related_name="contacts")
    prenom = models.CharField(max_length=80, blank=True)
    nom = models.CharField(max_length=120)
    fonction = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=15, choices=regles.ROLES, default="utilisateur")
    email = models.EmailField(blank=True)
    statut_email = models.CharField(max_length=10, choices=regles.STATUTS_EMAIL, default="absent")
    telephone = models.CharField(max_length=30, blank=True)
    linkedin_url = models.URLField("Profil LinkedIn", blank=True)
    oppose = models.BooleanField(default=False)
    informe_le = models.DateTimeField("Informé (RGPD) le", null=True, blank=True)
    dernier_contact_entrant_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["compte", "nom"]

    def __str__(self):
        return self.nom_complet

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}".strip()


class Signal(models.Model):
    compte = models.ForeignKey(Compte, on_delete=models.CASCADE, related_name="signaux")
    type = models.CharField(max_length=20, choices=regles.SIGNAL_CHOICES)
    texte = models.CharField(max_length=300)
    source = models.CharField(max_length=120)
    url = models.URLField(blank=True)
    date_signal = models.DateField(default=date.today)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["-date_signal"]

    def __str__(self):
        return f"{self.get_type_display()} · {self.compte}"

    @property
    def age_jours(self) -> int:
        return max(0, (timezone.localdate() - self.date_signal).days)


class HistoriqueFormation(models.Model):
    compte = models.ForeignKey(Compte, null=True, blank=True, on_delete=models.SET_NULL, related_name="formations")
    siren = models.CharField(max_length=9, blank=True)
    nom_client = models.CharField("Client", max_length=255)
    prestation = models.CharField(max_length=40, choices=regles.PRESTATION_CHOICES)
    date_session = models.DateField()
    nb_stagiaires = models.PositiveIntegerField(default=1)
    formateur = models.CharField(max_length=120, blank=True)
    reference_planif_st = models.CharField("Référence Planif ST", max_length=60, blank=True)
    source = models.CharField(max_length=20, default="saisie")
    relance_creee = models.BooleanField(default=False)

    class Meta:
        ordering = ["date_session"]
        verbose_name = "formation réalisée"
        verbose_name_plural = "historique des formations"

    def __str__(self):
        return f"{self.prestation} · {self.nom_client} · {self.date_session:%d/%m/%Y}"

    @property
    def echeance(self) -> date:
        mois, _ = regles.ECHEANCES.get(self.prestation, (24, 60))
        m = self.date_session.month - 1 + mois
        annee, mois_ = self.date_session.year + m // 12, m % 12 + 1
        import calendar
        jour = min(self.date_session.day, calendar.monthrange(annee, mois_)[1])
        return date(annee, mois_, jour)

    @property
    def jours_restants(self) -> int:
        return (self.echeance - timezone.localdate()).days

    @property
    def etat(self) -> str:
        _, relance = regles.ECHEANCES.get(self.prestation, (24, 60))
        j = self.jours_restants
        return "retard" if j < 0 else ("relancer" if j <= relance else "ok")


class Tache(models.Model):
    TYPES = [("appel", "Appel"), ("email", "E-mail"), ("linkedin", "LinkedIn"), ("qualifier", "Qualification"), ("autre", "Autre")]
    compte = models.ForeignKey(Compte, null=True, blank=True, on_delete=models.CASCADE, related_name="taches")
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL)
    type = models.CharField(max_length=10, choices=TYPES, default="appel")
    titre = models.CharField(max_length=255)
    echeance = models.DateField(default=date.today)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    faite_le = models.DateTimeField(null=True, blank=True)
    origine = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["faite_le", "echeance"]

    def __str__(self):
        return self.titre

    @property
    def retard(self) -> int:
        return (timezone.localdate() - self.echeance).days


class Activite(models.Model):
    """Historique de la fiche : e-mails préparés, appels, notes, actions LinkedIn, changements."""

    TYPES = [("note", "Note"), ("email", "E-mail"), ("appel", "Appel"), ("linkedin", "LinkedIn"), ("statut", "Statut"), ("systeme", "Système")]
    compte = models.ForeignKey(Compte, on_delete=models.CASCADE, related_name="activites")
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL)
    type = models.CharField(max_length=10, choices=TYPES, default="note")
    texte = models.TextField()
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]


class Opposition(models.Model):
    valeur = models.CharField("E-mail ou domaine (@domaine.fr)", max_length=255, unique=True)
    source = models.CharField(max_length=120, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return self.valeur

    def save(self, *args, **kwargs):
        self.valeur = self.valeur.strip().lower()
        super().save(*args, **kwargs)


class ReportAction(models.Model):
    """Action de « Ma journée » reportée ou marquée faite (pour ne plus l'afficher aujourd'hui)."""

    cle = models.CharField(max_length=40)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    jour = models.DateField(default=date.today)
    faite = models.BooleanField(default=False)

    class Meta:
        unique_together = [("cle", "utilisateur", "jour")]


# ---------------------------------------------------------------- LinkedIn (option)


class ConnexionLinkedIn(models.Model):
    """Compte LinkedIn connecté par un utilisateur (OAuth officiel : identité + publication)."""

    utilisateur = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="linkedin")
    sub = models.CharField("Identifiant LinkedIn", max_length=80)
    nom = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    photo = models.URLField(max_length=800, blank=True)
    jeton = models.TextField()
    expire_le = models.DateTimeField()
    portees = models.CharField(max_length=200, blank=True)
    connecte_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "connexion LinkedIn"
        verbose_name_plural = "connexions LinkedIn"

    def __str__(self):
        return f"{self.nom} ({self.utilisateur})"

    @property
    def valide(self) -> bool:
        return self.expire_le > timezone.now()

    @property
    def peut_publier(self) -> bool:
        return "w_member_social" in self.portees


class PublicationLinkedIn(models.Model):
    STATUTS = [("brouillon", "Brouillon"), ("publiee", "Publiée"), ("erreur", "Erreur")]
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    texte = models.TextField()
    statut = models.CharField(max_length=10, choices=STATUTS, default="brouillon")
    urn = models.CharField(max_length=120, blank=True)
    erreur = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    publiee_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "publication LinkedIn"


class ActionLinkedIn(models.Model):
    """Action faite à la main sur LinkedIn, notée dans l'agent (sert aux plafonds et à l'historique)."""

    TYPES = [("profil", "Profil consulté"), ("invitation", "Invitation envoyée"), ("message", "Message envoyé")]
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    compte = models.ForeignKey(Compte, null=True, blank=True, on_delete=models.CASCADE)
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL)
    type = models.CharField(max_length=12, choices=TYPES)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]


# ---------------------------------------------------------------- Profil et catalogue (propres à l'outil)


class ProfilEntreprise(models.Model):
    """Ce que l'IA sait de FORMA'ST pour rédiger. Modifiable dans Paramètres, ou repris de FORM'AO."""

    nom = models.CharField(max_length=150, default="FORMA'ST")
    presentation = models.TextField(blank=True, default=(
        "Organisme de formation en santé et sécurité au travail : secourisme (SST, MAC SST), incendie et évacuation, "
        "gestes et postures / TMS, QVT / RPS. Interventions partout en France, avec un interlocuteur unique."))
    habilitations = models.CharField(max_length=255, blank=True, default="Qualiopi ; habilitation INRS pour la formation SST")
    points_forts = models.TextField(blank=True, default=(
        "Unité mobile de formation incendie (UMFI) et bac à flammes\nFormateurs sapeurs-pompiers\n"
        "Distanciel sur Teams\nOrganisation nationale multi-sites avec contact unique"))
    references_citables = models.TextField("Références citables", blank=True, help_text="Une par ligne. Seules ces références peuvent apparaître dans un message.")
    synchronise_le = models.DateTimeField("Repris de FORM'AO le", null=True, blank=True)

    class Meta:
        verbose_name = "profil de l'entreprise"
        verbose_name_plural = "profil de l'entreprise"

    def __str__(self):
        return self.nom

    @classmethod
    def get(cls) -> "ProfilEntreprise":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def texte_pour_ia(self) -> str:
        lignes = [f"# Profil de l'entreprise\nNom : {self.nom}", self.presentation, f"Habilitations : {self.habilitations or 'non renseignées'}"]
        if self.points_forts:
            lignes.append("Points forts :\n" + "\n".join(f"- {p}" for p in self.points_forts.splitlines() if p.strip()))
        lignes.append("Références citables :\n" + ("\n".join(f"- {r}" for r in self.references_citables.splitlines() if r.strip()) or "aucune (n'en cite pas)"))
        return "\n\n".join(lignes)


class Prestation(models.Model):
    """Catalogue utilisé uniquement pour estimer le potentiel (aucun devis dans cet outil)."""

    USAGES = [("sst", "SST initial"), ("mac", "MAC SST"), ("gp", "Gestes et postures"), ("incendie", "Incendie / évacuation"), ("autre", "Autre")]
    intitule = models.CharField(max_length=200)
    usage_potentiel = models.CharField("Sert au calcul de", max_length=10, choices=USAGES, default="autre")
    duree = models.CharField(max_length=50, blank=True)
    prix_intra_ht = models.DecimalField("Prix intra HT (session)", max_digits=10, decimal_places=2, null=True, blank=True)
    exemple = models.BooleanField("Tarif d'exemple", default=False, help_text="Décochez quand le prix est le vôtre.")
    actif = models.BooleanField(default=True)
    reference_formao = models.CharField(max_length=40, blank=True, editable=False)

    class Meta:
        ordering = ["usage_potentiel", "intitule"]
        verbose_name = "prestation du catalogue"
        verbose_name_plural = "catalogue"

    def __str__(self):
        return self.intitule



# ---------------------------------------------------------------- Phase 2 : messagerie et séquences


class BoiteEnvoi(models.Model):
    """Boîte d'envoi (SMTP) et de relève des réponses (IMAP). Mots de passe : comptes dédiés, mots de passe d'application."""

    nom = models.CharField(max_length=80, help_text="Ex. « Julie – prospection »")
    adresse = models.EmailField(unique=True)
    nom_affiche = models.CharField("Nom affiché", max_length=120, blank=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="boites_envoi")
    smtp_hote = models.CharField("Serveur SMTP", max_length=120)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_securite = models.CharField(max_length=8, choices=[("starttls", "STARTTLS (587)"), ("ssl", "SSL (465)"), ("aucune", "Aucune")], default="starttls")
    smtp_identifiant = models.CharField(max_length=150, blank=True)
    smtp_mot_de_passe = models.CharField(max_length=200, blank=True)
    imap_hote = models.CharField("Serveur IMAP (réponses)", max_length=120, blank=True)
    imap_port = models.PositiveIntegerField(default=993)
    imap_identifiant = models.CharField(max_length=150, blank=True)
    imap_mot_de_passe = models.CharField(max_length=200, blank=True)
    imap_dernier_uid = models.PositiveIntegerField(default=0, editable=False)
    plafond_jour = models.PositiveSmallIntegerField("Envois max. par jour", default=40)
    signature = models.TextField(blank=True, help_text="Remplace [Prénom Nom] et [Téléphone] dans les messages.")
    actif = models.BooleanField(default=True)
    derniere_erreur = models.TextField(blank=True, editable=False)

    class Meta:
        verbose_name = "boîte d'envoi"
        verbose_name_plural = "boîtes d'envoi"

    def __str__(self):
        return f"{self.nom} <{self.adresse}>"

    def envoyes_aujourd_hui(self) -> int:
        debut = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.messages.filter(sens="sortant", statut="envoye", envoye_le__gte=debut).count()


class Sequence(models.Model):
    MODES = [("brouillon", "Chaque e-mail validé"), ("premier", "Premier e-mail validé, la suite automatique"), ("auto", "Tout automatique (modèles validés)")]
    nom = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    mode_validation = models.CharField(max_length=10, choices=MODES, default="premier")
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class EtapeSequence(models.Model):
    TYPES = [("email", "E-mail"), ("linkedin", "Tâche LinkedIn"), ("appel", "Appel"), ("tache", "Tâche libre")]
    sequence = models.ForeignKey(Sequence, on_delete=models.CASCADE, related_name="etapes")
    ordre = models.PositiveSmallIntegerField(default=1)
    type = models.CharField(max_length=10, choices=TYPES, default="email")
    delai_jours = models.PositiveSmallIntegerField("Jours après l'étape précédente", default=0)
    canal_redaction = models.CharField(max_length=10, choices=[("email", "Premier e-mail"), ("relance", "Relance")], default="email",
                                       help_text="Texte proposé par l'outil si l'objet et le corps sont vides.")
    objet = models.CharField(max_length=200, blank=True, help_text="Variables : {entreprise}, {prenom}, {nom}, {besoin_sst}, {signal}")
    corps = models.TextField(blank=True, help_text="Vide = texte rédigé par l'outil pour chaque prospect, à partir de sa fiche.")
    intitule = models.CharField("Intitulé de la tâche", max_length=200, blank=True)

    class Meta:
        ordering = ["sequence", "ordre"]

    def __str__(self):
        return f"{self.sequence} · étape {self.ordre} ({self.get_type_display()})"


class Inscription(models.Model):
    STATUTS = [("active", "Active"), ("pause", "En pause"), ("terminee", "Terminée"), ("arretee", "Arrêtée")]
    sequence = models.ForeignKey(Sequence, on_delete=models.CASCADE, related_name="inscriptions")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="inscriptions")
    etape_suivante = models.PositiveSmallIntegerField(default=1)
    statut = models.CharField(max_length=10, choices=STATUTS, default="active")
    prochaine_le = models.DateTimeField(default=timezone.now)
    motif_arret = models.CharField(max_length=200, blank=True)
    inscrit_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    boite = models.ForeignKey(BoiteEnvoi, null=True, blank=True, on_delete=models.SET_NULL)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.contact} · {self.sequence}"


class Message(models.Model):
    STATUTS = [("a_valider", "À valider"), ("programme", "Programmé"), ("envoi", "Envoi en cours"), ("envoye", "Envoyé"),
               ("erreur", "Erreur"), ("annule", "Annulé"), ("recu", "Reçu")]
    CLASSES = [("interesse", "Intéressé"), ("pas_maintenant", "Pas maintenant"), ("mauvais_interlocuteur", "Mauvais interlocuteur"),
               ("deja_equipe", "Déjà équipé"), ("absence", "Absence"), ("opposition", "Opposition"), ("rebond", "Rebond"), ("autre", "À lire")]
    compte = models.ForeignKey(Compte, null=True, blank=True, on_delete=models.CASCADE, related_name="messages")
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    boite = models.ForeignKey(BoiteEnvoi, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    inscription = models.ForeignKey(Inscription, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    sens = models.CharField(max_length=8, choices=[("sortant", "Envoyé"), ("entrant", "Reçu")], default="sortant")
    destinataire = models.EmailField(blank=True)
    expediteur = models.CharField(max_length=255, blank=True)
    objet = models.CharField(max_length=255)
    corps = models.TextField()
    statut = models.CharField(max_length=10, choices=STATUTS, default="a_valider")
    prevu_le = models.DateTimeField(null=True, blank=True)
    envoye_le = models.DateTimeField(null=True, blank=True)
    message_id = models.CharField(max_length=255, blank=True, db_index=True)
    en_reponse_a = models.CharField(max_length=255, blank=True)
    redirige_test = models.BooleanField(default=False)
    erreur = models.TextField(blank=True)
    note_qualite = models.PositiveSmallIntegerField(null=True, blank=True)
    valide_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    classe = models.CharField(max_length=25, choices=CLASSES, blank=True)
    confiance = models.PositiveSmallIntegerField(null=True, blank=True)
    date_reprise = models.DateField(null=True, blank=True)
    traite = models.BooleanField(default=False)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.get_sens_display()} · {self.objet}"


# ---------------------------------------------------------------- Phase 3 : recherche automatique de prospects


class RechercheAuto(models.Model):
    """Profil de recherche exécuté chaque nuit dans les sources publiques gratuites."""

    SOURCES = [("sirene", "Annuaire des entreprises (cible)"), ("bodacc", "BODACC (nouveaux établissements)"), ("georisques", "Géorisques (sites ICPE)"),
               ("francetravail", "France Travail (offres d'emploi)")]
    nom = models.CharField(max_length=120)
    source = models.CharField(max_length=20, choices=SOURCES, default="sirene")
    actif = models.BooleanField(default=True)
    codes_naf = models.TextField("Codes NAF", blank=True, help_text="Un par ligne : code exact (52.10B) ou division (10 = toute l'industrie agroalimentaire).")
    departements = models.CharField("Départements", max_length=400, blank=True, help_text="Séparés par des virgules. Vide = France entière.")
    effectif_min = models.PositiveIntegerField("Effectif minimum", default=50)
    effectif_max = models.PositiveIntegerField("Effectif maximum", default=0, help_text="0 = sans limite. Ex. 2000 pour écarter les très grands groupes.")
    etablissements_min = models.PositiveIntegerField("Établissements minimum", default=1, help_text="2 ou plus pour viser les réseaux multi-sites.")
    segment = models.CharField(max_length=20, choices=regles.SEGMENT_CHOICES, blank=True, help_text="Vide = déduit du code NAF.")
    mots_cles = models.CharField("Mots-clés (France Travail)", max_length=255, blank=True,
                                 help_text="Séparés par des virgules, ex. QSE, HSE, responsable sécurité. Vide = recrutements en nombre par secteur.")
    seuil_offres = models.PositiveSmallIntegerField("Offres min. par entreprise", default=10, help_text="Pour les recrutements en nombre (France Travail).")
    palier_min = models.CharField("Adéquation minimale", max_length=1, default="B",
                                  choices=[("A", "Forte (80 et plus)"), ("B", "Bonne (65 et plus)"), ("C", "Toutes")])
    max_par_nuit = models.PositiveSmallIntegerField("Nouveaux prospects max. par nuit", default=15)
    mois_actifs = models.CharField("Mois actifs", max_length=40, blank=True, help_text="Ex. 9,10,11. Vide = toute l'année.")
    page_suivante = models.PositiveIntegerField(default=1, editable=False)
    derniere_execution = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-actif", "nom"]
        verbose_name = "recherche automatique"
        verbose_name_plural = "recherches automatiques"

    def __str__(self):
        return self.nom

    def liste_naf(self) -> list[str]:
        return [x.strip().upper() for x in self.codes_naf.replace(",", "\n").splitlines() if x.strip()]

    def liste_departements(self) -> list[str]:
        return [d.strip().upper() for d in self.departements.replace(";", ",").split(",") if d.strip()]

    def active_ce_mois(self, mois: int | None = None) -> bool:
        mois = mois or timezone.localdate().month
        m = [int(x) for x in self.mois_actifs.replace(";", ",").split(",") if x.strip().isdigit()]
        return not m or mois in m


class ExecutionRecherche(models.Model):
    recherche = models.ForeignKey(RechercheAuto, on_delete=models.CASCADE, related_name="executions")
    debut = models.DateTimeField(auto_now_add=True)
    examines = models.PositiveIntegerField(default=0)
    crees = models.PositiveIntegerField(default=0)
    signaux = models.PositiveIntegerField(default=0)
    ignores = models.PositiveIntegerField(default=0)
    erreur = models.TextField(blank=True)
    comptes = models.ManyToManyField(Compte, blank=True, related_name="trouve_par")

    class Meta:
        ordering = ["-debut"]
