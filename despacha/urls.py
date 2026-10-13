from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import path, include
from django.views.generic import RedirectView

admin.site.site_header = "Administración Despacha"
admin.site.site_title  = "Despacha"
admin.site.index_title = "Panel de administración"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="lista_cortes"), name="home"),
    path(
        "login/",
        LoginView.as_view(
            template_name="admin/login.html",
            extra_context={"app_path": "/login/"},
        ),
        name="login",
    ),
    path("admin/", admin.site.urls),
    path("admin-auditoria/", include("core.urls")),
    path("cortes/", include("cortes.urls")),
    path("api/v1/siigo/", include("integraciones_siigo.urls")),
    path("api/v1/vigia/", include("api_vigia.urls")),
]
