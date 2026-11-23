from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/prospection/", permanent=False)),
    path("connexion/", auth_views.LoginView.as_view(template_name="prospection/connexion.html", redirect_authenticated_user=True), name="connexion"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),
    path("prospection/", include("prospection.urls")),
    path("admin/", admin.site.urls),
]
