from django.urls import path

from . import views

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
    path("linkedin/", views.linkedin_page, name="linkedin"),
    path("linkedin/connecter/", views.linkedin_connecter, name="linkedin_connecter"),
    path("linkedin/retour/", views.linkedin_retour, name="linkedin_retour"),
    path("linkedin/deconnecter/", views.linkedin_deconnecter, name="linkedin_deconnecter"),
    path("linkedin/publier/", views.linkedin_publier, name="linkedin_publier"),
    path("linkedin/publication/<int:pk>/publier/", views.linkedin_republier, name="linkedin_republier"),
]
