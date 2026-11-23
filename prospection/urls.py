from django.urls import path

from . import views, views_envoi, views_recherche

app_name = "prospection"

urlpatterns = [
    path("", views.journee, name="journee"),
    path("journee/action/", views.journee_action, name="journee_action"),
    path("prospects/", views.prospects, name="prospects"),
    path("compte/nouveau/", views.compte_nouveau, name="compte_nouveau"),
    path("compte/<int:pk>/", views.compte, name="compte"),
    path("compte/<int:pk>/action/", views.compte_action, name="compte_action"),
    path("import/", views.import_fichier, name="import"),
    path("import/<int:pk>/", views.import_detail, name="import_detail"),
    path("import/<int:pk>/annuler/", views.import_annuler, name="import_annuler"),
    path("import/acheteurs-ao/", views.acheteurs_ao, name="acheteurs_ao"),
    path("formao/synchroniser/", views.formao_synchroniser, name="formao_synchroniser"),
    path("historique/", views.historique, name="historique"),
    path("historique/relancer/", views.historique_relancer, name="historique_relancer"),
    path("taches/", views.taches, name="taches"),
    path("opposition/", views.oppositions, name="oppositions"),
    path("sequences/", views_envoi.sequences, name="sequences"),
    path("sequences/<int:pk>/", views_envoi.sequence, name="sequence"),
    path("sequences/inscrire/", views_envoi.inscrire, name="inscrire"),
    path("sequences/inscription/<int:pk>/arreter/", views_envoi.desinscrire, name="desinscrire"),
    path("messagerie/", views_envoi.messagerie_page, name="messagerie"),
    path("compte/<int:pk>/envoyer/", views_envoi.envoyer_depuis_fiche, name="envoyer"),
    path("reponses/", views_envoi.reponses_page, name="reponses"),
    path("statistiques/", views_envoi.statistiques, name="statistiques"),
    path("recherche-automatique/", views_recherche.recherches, name="recherches"),
    path("linkedin/", views.linkedin_page, name="linkedin"),
    path("linkedin/connecter/", views.linkedin_connecter, name="linkedin_connecter"),
    path("linkedin/retour/", views.linkedin_retour, name="linkedin_retour"),
    path("linkedin/deconnecter/", views.linkedin_deconnecter, name="linkedin_deconnecter"),
    path("linkedin/publier/", views.linkedin_publier, name="linkedin_publier"),
    path("linkedin/publication/<int:pk>/publier/", views.linkedin_republier, name="linkedin_republier"),
]
