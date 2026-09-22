from django.urls import path

from . import views


app_name = "api_vigia"

urlpatterns = [
    path("cortes", views.listar_cortes, name="listar_cortes"),
    path("cortes/<int:corte_id>", views.detalle_corte, name="detalle_corte"),
    path("documentos", views.documentos_dia, name="documentos_dia"),
]
