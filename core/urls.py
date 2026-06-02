from django.urls import path

from . import views

urlpatterns = [
    path("", views.AuditoriaListView.as_view(), name="admin_auditoria"),
    path("config/", views.PanelConfigView.as_view(), name="panel_config"),
]
