from django.urls import path

from . import views

urlpatterns = [
    path("", views.ListaCortesView.as_view(), name="lista_cortes"),
    path("cargar/", views.CargarCorteView.as_view(), name="cargar_corte"),
    path("<int:pk>/", views.DetalleCorteView.as_view(), name="detalle_corte"),
    path("<int:pk>/editar/", views.EditarCorteView.as_view(), name="editar_corte"),
    path("<int:pk>/split/", views.SplitDocumentoView.as_view(), name="split_documento"),
    path("<int:pk>/deshacer-split/", views.DeshacerSplitView.as_view(), name="deshacer_split"),
    path("<int:pk>/forzar-liberacion/", views.ForzarLiberacionView.as_view(), name="forzar_liberacion"),
    path("<int:pk>/generar/", views.GenerarCorteView.as_view(), name="generar_corte"),
]
