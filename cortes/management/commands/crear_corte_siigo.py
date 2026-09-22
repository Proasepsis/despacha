from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from cortes.servicios.cargar import ErrorCarga, ErrorDuplicado, ErrorSugerirAdicional
from cortes.servicios.cargar_ingesta import cargar_ingesta
from integraciones_siigo.models import IngestionSiigo


class Command(BaseCommand):
    help = "Crea un Corte desde una ingesta SIIGO recibida."

    def add_arguments(self, parser):
        parser.add_argument(
            "--extraction-id",
            help="UUID de la ingesta. Si se omite se usa la más reciente.",
        )
        parser.add_argument("--numero-corte", type=int, choices=[1, 2])
        parser.add_argument("--fecha", help="Fecha del corte (YYYY-MM-DD).")
        parser.add_argument(
            "--usuario",
            help="Usuario que figurará como responsable (por defecto el primer admin).",
        )
        parser.add_argument(
            "--es-adicional", action="store_true", help="Marcar como corte adicional."
        )

    def handle(self, *args, **options):
        ingestion = self._select_ingestion(options["extraction_id"])
        usuario = self._select_usuario(options["usuario"])
        fecha = options["fecha"]

        try:
            corte, resultado = cargar_ingesta(
                ingestion,
                usuario=usuario,
                numero_corte=options["numero_corte"],
                es_adicional=options["es_adicional"],
                fecha=fecha,
            )
        except (ErrorDuplicado, ErrorSugerirAdicional, ErrorCarga) as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f"{corte.display_corte} {corte.fecha:%d/%m/%Y} creado — "
                f"{resultado.documentos_creados} documentos, "
                f"{resultado.lineas_creadas} líneas."
            )
        )

    def _select_ingestion(self, extraction_id):
        if extraction_id:
            return IngestionSiigo.objects.get(extraction_id=extraction_id)
        ingestion = IngestionSiigo.objects.order_by("-recibido_en").first()
        if ingestion is None:
            raise CommandError("No hay ingestas SIIGO recibidas.")
        return ingestion

    def _select_usuario(self, username):
        User = get_user_model()
        if username:
            return User.objects.get(username=username)
        usuario = User.objects.filter(is_superuser=True).order_by("pk").first()
        if usuario is None:
            raise CommandError("No existe un usuario administrador.")
        return usuario
