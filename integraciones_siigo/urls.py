from django.urls import path

from .views import ingest_siigo


urlpatterns = [
    path("ingestions", ingest_siigo, name="siigo-ingestion"),
]
