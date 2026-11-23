from django.contrib import admin

from .models import (ActionLinkedIn, Activite, AppelIA, BoiteEnvoi, Compte, ConnexionLinkedIn, Contact, EtapeSequence, HistoriqueFormation, ImportFichier,
                     Inscription, Message, Opposition, Parametres, Prestation, ProfilEntreprise, PublicationLinkedIn, Sequence, Signal, Tache)
from .services.scoring import recalculer_tout

admin.site.site_header = "Forma Prospect · paramètres"
admin.site.site_title = "Forma Prospect"
admin.site.index_title = "Paramètres et données"
admin.site.site_url = "/prospection/"


@admin.register(Parametres)
class ParametresAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Score", {"fields": ["poids_adequation", "poids_intention", "poids_accessibilite", "seuil_palier_a", "seuil_palier_b",
                              "part_sst", "departements_prioritaires", "objectif_actions_jour"]}),
        ("Messagerie", {"fields": ["mode_test", "adresse_test", "plages_envoi"]}),
        ("Coûts IA", {"fields": ["budget_ia_mensuel", "bloquer_ia_au_budget", "taux_usd_eur"],
                      "description": "Suivi et simulateur dans le menu « Coûts IA »."}),
        ("Option LinkedIn", {"fields": ["linkedin_actif", "linkedin_invitations_semaine", "linkedin_profils_jour"],
                             "description": "Connexion du compte et publication par l'API officielle ; invitations et messages "
                                            "toujours envoyés à la main. Renseignez aussi LINKEDIN_CLIENT_ID et LINKEDIN_CLIENT_SECRET dans le .env."}),
    ]

    def has_add_permission(self, request):
        return not Parametres.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        n = recalculer_tout()
        self.message_user(request, f"Paramètres enregistrés, {n} scores recalculés.")


class ContactInline(admin.TabularInline):
    model = Contact
    extra = 0
    fields = ["prenom", "nom", "fonction", "role", "email", "statut_email", "telephone", "linkedin_url", "oppose"]


class SignalInline(admin.TabularInline):
    model = Signal
    extra = 0


@admin.register(Compte)
class CompteAdmin(admin.ModelAdmin):
    list_display = ["nom", "ville", "segment", "effectif", "palier", "score", "statut", "responsable"]
    list_filter = ["palier", "segment", "statut", "est_client"]
    search_fields = ["nom", "siren", "ville"]
    inlines = [ContactInline, SignalInline]
    readonly_fields = ["score", "score_adequation", "score_intention", "score_accessibilite", "palier", "explication", "sirene_le"]


@admin.register(HistoriqueFormation)
class HistoriqueAdmin(admin.ModelAdmin):
    list_display = ["nom_client", "prestation", "date_session", "nb_stagiaires", "echeance", "relance_creee"]
    list_filter = ["prestation", "relance_creee"]
    search_fields = ["nom_client", "siren"]


@admin.register(Tache)
class TacheAdmin(admin.ModelAdmin):
    list_display = ["titre", "type", "echeance", "assignee", "faite_le"]
    list_filter = ["type"]


@admin.register(Opposition)
class OppositionAdmin(admin.ModelAdmin):
    list_display = ["valeur", "source", "cree_le"]
    search_fields = ["valeur"]


@admin.register(ConnexionLinkedIn)
class ConnexionLinkedInAdmin(admin.ModelAdmin):
    list_display = ["utilisateur", "nom", "expire_le", "portees"]
    exclude = ["jeton"]


admin.site.register([ImportFichier, Activite, PublicationLinkedIn, ActionLinkedIn])


@admin.register(Prestation)
class PrestationAdmin(admin.ModelAdmin):
    list_display = ["intitule", "usage_potentiel", "duree", "prix_intra_ht", "exemple", "actif"]
    list_editable = ["prix_intra_ht", "exemple", "actif"]
    list_filter = ["usage_potentiel", "actif"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        recalculer_tout()


@admin.register(ProfilEntreprise)
class ProfilEntrepriseAdmin(admin.ModelAdmin):
    readonly_fields = ["synchronise_le"]

    def has_add_permission(self, request):
        return not ProfilEntreprise.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class EtapeInline(admin.TabularInline):
    model = EtapeSequence
    extra = 0


@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    list_display = ["nom", "mode_validation", "actif"]
    inlines = [EtapeInline]


@admin.register(BoiteEnvoi)
class BoiteEnvoiAdmin(admin.ModelAdmin):
    list_display = ["nom", "adresse", "smtp_hote", "plafond_jour", "actif"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["objet", "sens", "destinataire", "statut", "classe", "cree_le"]
    list_filter = ["sens", "statut", "classe"]
    search_fields = ["objet", "destinataire", "expediteur"]


admin.site.register(Inscription)


@admin.register(AppelIA)
class AppelIAAdmin(admin.ModelAdmin):
    list_display = ["cree_le", "usage", "modele", "tokens_entree", "tokens_cache_lus", "tokens_sortie", "cout_usd", "compte", "utilisateur"]
    list_filter = ["usage", "modele"]
    date_hierarchy = "cree_le"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
