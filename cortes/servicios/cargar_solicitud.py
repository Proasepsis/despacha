from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import date

from django.db import transaction

from cortes.models import Corte
from cortes.servicios.cargar import _siguiente_letra_adicional
from cortes.servicios.cargar_ingesta import FORMATO_API_SIIGO
from cortes.servicios.procesar import procesar_documentos_internos
from core.adaptadores.api_siigo.convertir import filas_a_documentos_internos
from core.servicios.notificaciones import notificar_sin_maestra_detectado

log = logging.getLogger(__name__)


def cargar_cortes_de_solicitud(solicitud, ingestion) -> list[Corte]:
    """Crea un corte 'Solicitud' por cada día con documentos de la foto completa que trajo la solicitud.

    Entra el día completo, también lo que ya está en otros cortes (el detalle lo marca 'ya en Corte X').
    Es idempotente: si ese día ya tiene un corte de solicitud con las mismas filas, no se repite.
    """
    por_dia: dict[date, list[dict]] = defaultdict(list)
    for fila in ingestion.payload["rows"]:
        dia = date(int(fila["anio_documento"]), int(fila["mes_documento"]), int(fila["dia_documento"]))
        por_dia[dia].append(fila)

    cortes = []
    for dia, filas in sorted(por_dia.items()):
        documentos = filas_a_documentos_internos(filas)
        if not documentos:
            continue
        hash_sha256 = hashlib.sha256(
            json.dumps(filas, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        if Corte.objects.filter(
            numero_corte=Corte.NUMERO_SOLICITUD, fecha=dia, hash_sha256=hash_sha256
        ).exists():
            continue
        # Un mismo día puede pedirse varias veces: la primera es 'Solicitud', las siguientes 'Solicitud A'...
        base = Corte.objects.filter(fecha=dia, numero_corte=Corte.NUMERO_SOLICITUD, adicional_letra="")
        letra = _siguiente_letra_adicional(dia, Corte.NUMERO_SOLICITUD) if base.exists() else ""
        with transaction.atomic():
            corte = Corte.objects.create(
                archivo=f"siigo-solicitud-{solicitud.solicitud_id}-{dia:%Y%m%d}.json",
                formato_origen=FORMATO_API_SIIGO,
                hash_sha256=hash_sha256,
                usuario_carga=solicitud.creada_por,
                fecha=dia,
                numero_corte=Corte.NUMERO_SOLICITUD,
                adicional_letra=letra,
                solicitud=solicitud,
                estado="cargado",
            )
            resultado = procesar_documentos_internos(corte, documentos)
            corte.estado = "en_revision"
            corte.save(update_fields=["estado"])
        if resultado.productos_nuevos_detectados:
            notificar_sin_maestra_detectado(corte, resultado.productos_nuevos_detectados)
        cortes.append(corte)
    return cortes
