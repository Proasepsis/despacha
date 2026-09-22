from django.contrib import admin, messages

from cortes.servicios.cargar import (
    ErrorCarga,
    ErrorDuplicado,
    ErrorSugerirAdicional,
)
from cortes.servicios.cargar_ingesta import cargar_ingesta

from .models import IngestionSiigo


@admin.register(IngestionSiigo)
class IngestionSiigoAdmin(admin.ModelAdmin):
    list_display = (
        "extraction_id",
        "window_start",
        "window_end",
        "row_count",
        "estado",
        "recibido_en",
    )
    list_filter = ("estado", "source", "schema_version")
    search_fields = ("extraction_id", "raw_sha256", "rows_sha256")
    readonly_fields = (
        "extraction_id",
        "schema_version",
        "source",
        "window_start",
        "window_end",
        "generated_at",
        "raw_sha256",
        "raw_size_bytes",
        "content_sha256",
        "rows_sha256",
        "row_count",
        "payload",
        "source_ip",
        "estado",
        "recibido_en",
    )
    actions = ["procesar_como_corte"]

    @admin.action(description="Crear corte desde esta ingesta")
    def procesar_como_corte(self, request, queryset):
        creados = 0
        errores = []
        for ingestion in queryset:
            try:
                corte, resultado = cargar_ingesta(
                    ingestion,
                    usuario=request.user,
                    numero_corte=None,
                    es_adicional=False,
                )
                creados += 1
                messages.success(
                    request,
                    f"{corte.display_corte} {corte.fecha:%d/%m/%Y} creado "
                    f"({resultado.documentos_creados} docs, "
                    f"{resultado.lineas_creadas} líneas).",
                )
            except ErrorDuplicado as error:
                errores.append(f"{ingestion.extraction_id}: {error}")
            except ErrorSugerirAdicional as error:
                errores.append(f"{ingestion.extraction_id}: {error}")
            except ErrorCarga as error:
                errores.append(f"{ingestion.extraction_id}: {error}")
            except Exception as error:
                errores.append(f"{ingestion.extraction_id}: {error}")

        if errores:
            self.message_user(
                request,
                f"{creados} cortes creados. Errores: " + " | ".join(errores),
                level=messages.WARNING,
            )
