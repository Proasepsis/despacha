from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

admin.site.site_header = "Administración Despacha"
admin.site.site_title  = "Despacha"
admin.site.index_title = "Panel de administración"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="lista_cortes"), name="home"),
    path("admin/", admin.site.urls),
    path("admin-auditoria/", include("core.urls")),
    path("cortes/", include("cortes.urls")),
]
