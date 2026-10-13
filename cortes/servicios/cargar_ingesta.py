from __future__ import annotations

import hashlib
from datetime import date as date_type

from django.contrib.auth.models import User
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime

from cortes.models import Corte
from cortes.servicios.cargar import (
    ErrorCarga,
    ErrorDuplicado,
    ErrorSugerirAdicional,
    _siguiente_letra_adicional,
)
from cortes.servicios.corte_por_hora import BOGOTA, sugerir_corte, ventana_corte
from cortes.servicios.procesar import (
    procesar_documentos_internos,
    ResultadoProcesamiento,
)
from core.adaptadores.api_siigo.convertir import filas_a_documentos_internos
from core.servicios.notificaciones import notificar_sin_maestra_detectado

FORMATO_API_SIIGO = "API_SIIGO"

# El extractor llama corte_1 a la corrida de las 11:00 (mañana) y corte_2 a la de las 16:00 (tarde);
# en Despacha la mañana es el Corte 2 y la tarde el Corte 1.
NUMERO_POR_CUT = {"corte_1": 2, "corte_2": 1}


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
    # Un envío sin movimiento (rows vacío, o nada que aplique a Despacha) queda registrado, pero no crea corte
    if not documentos:
        raise ErrorCarga("La ingesta no trae documentos para Despacha; no se crea corte.")

    cut = ingestion.payload.get("cut")
    es_solicitud = bool(cut) and cut.get("nombre") == "solicitud"
    hash_sha256 = ingestion.rows_sha256
    if not es_solicitud:
        existente = Corte.objects.filter(hash_sha256=hash_sha256).first()
        if existente:
            raise ErrorDuplicado(corte_existente_id=existente.pk)

    if cut and not es_solicitud:
        # Schema 1.1: el extractor ya filtró por su ventana (desde, hasta]; no se vuelve a filtrar
        # para no perder documentos en los bordes. Sus nombres van al revés de los de Despacha.
        numero = numero_corte or NUMERO_POR_CUT.get(cut["nombre"]) or sugerir_corte(ingestion.generated_at)
        hasta = parse_datetime(cut["hasta"]).astimezone(BOGOTA)
        fecha_corte = _coerce_date(fecha) or hasta.date()
    else:
        # Sin número explícito, se deduce de cuándo se extrajo (11:00 → corte 2, 16:00 → corte 1)
        numero = numero_corte or sugerir_corte(ingestion.generated_at)
        # Una solicitud trae el día completo: se carga el corte elegido con los documentos de su franja
        dia = parse_date(cut["hasta"]) if es_solicitud else ingestion.window_end
        fecha_corte = _coerce_date(fecha) or _coerce_date(dia)

        # Solo los documentos de la franja del corte; los que no traen hora se conservan
        inicio, fin = ventana_corte(fecha_corte, numero)
        documentos = [
            d for d in documentos
            if d.actualizado_en is None or inicio <= d.actualizado_en < fin
        ]
        if not documentos:
            raise ErrorCarga(
                f"La ingesta no tiene documentos en la franja del corte {numero} "
                f"({inicio:%d/%m %H:%M} a {fin:%d/%m %H:%M})."
            )

    if es_solicitud:
        # La misma foto del día se puede cargar como Corte 1 y como Corte 2, pero no dos veces como el mismo
        hash_sha256 = hashlib.sha256(f"{ingestion.rows_sha256}:{fecha_corte}:{numero}".encode()).hexdigest()
        existente = Corte.objects.filter(hash_sha256=hash_sha256).first()
        if existente:
            raise ErrorDuplicado(corte_existente_id=existente.pk)

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
