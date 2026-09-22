from __future__ import annotations

from datetime import date as date_type

from django.contrib.auth.models import User
from django.db import transaction
from django.utils.dateparse import parse_date

from cortes.models import Corte
from cortes.servicios.cargar import (
    ErrorCarga,
    ErrorDuplicado,
    ErrorSugerirAdicional,
    _siguiente_letra_adicional,
)
from cortes.servicios.corte_por_hora import sugerir_corte
from cortes.servicios.procesar import (
    procesar_documentos_internos,
    ResultadoProcesamiento,
)
from core.adaptadores.api_siigo.convertir import filas_a_documentos_internos
from core.servicios.notificaciones import notificar_sin_maestra_detectado

FORMATO_API_SIIGO = "API_SIIGO"


@transaction.atomic
def cargar_ingesta(
    ingestion,
    usuario: User,
    numero_corte: int | None = None,
    es_adicional: bool = False,
    fecha: date_type | None = None,
) -> tuple[Corte, ResultadoProcesamiento]:
    """Crea un Corte a partir de una ingesta SIIGO ya recibida.

    La deduplicación se apoya en ``IngestionSiigo.rows_sha256``, por lo que la
    misma fotografía de datos no puede generar dos cortes.
    """
    filas = ingestion.payload.get("rows", [])
    documentos = filas_a_documentos_internos(filas)

    hash_sha256 = ingestion.rows_sha256
    existente = Corte.objects.filter(hash_sha256=hash_sha256).first()
    if existente:
        raise ErrorDuplicado(corte_existente_id=existente.pk)

    numero = numero_corte or sugerir_corte()
    fecha_corte = _coerce_date(fecha) or _coerce_date(ingestion.window_end)

    if not es_adicional:
        if Corte.objects.filter(
            fecha=fecha_corte, numero_corte=numero, adicional_letra=""
        ).exists():
            raise ErrorSugerirAdicional(numero, fecha_corte)

    adicional_letra = (
        _siguiente_letra_adicional(fecha_corte, numero) if es_adicional else ""
    )

    try:
        corte = Corte.objects.create(
            archivo=f"siigo-{ingestion.extraction_id}.json",
            formato_origen=FORMATO_API_SIIGO,
            hash_sha256=hash_sha256,
            usuario_carga=usuario,
            fecha=fecha_corte,
            numero_corte=numero,
            adicional_letra=adicional_letra,
            estado="cargado",
        )
    except Exception as error:
        if not es_adicional:
            raise ErrorSugerirAdicional(numero, fecha_corte) from error
        raise ErrorCarga(f"No se pudo crear el corte: {error}") from error

    try:
        resultado = procesar_documentos_internos(corte, documentos)
    except Exception:
        corte.estado = "con_error"
        corte.save(update_fields=["estado"])
        raise

    corte.estado = "en_revision"
    corte.save(update_fields=["estado", "fecha"])

    if resultado.productos_nuevos_detectados:
        notificar_sin_maestra_detectado(corte, resultado.productos_nuevos_detectados)

    return corte, resultado


def _coerce_date(value):
    if value is None or isinstance(value, date_type):
        return value
    if isinstance(value, str):
        return parse_date(value)
    return value
