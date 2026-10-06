from django.urls import path

from .views import estado_solicitud, ingest_siigo, tomar_solicitud


urlpatterns = [
    path("ingestions", ingest_siigo, name="siigo-ingestion"),
    path("solicitudes/tomar", tomar_solicitud, name="siigo-solicitud-tomar"),
    path("solicitudes/<uuid:solicitud_id>/estado", estado_solicitud, name="siigo-solicitud-estado"),
]
