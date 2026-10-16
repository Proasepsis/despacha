from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from cortes.models import Documento, DocumentoDescartado
from core.adaptadores.api_siigo.convertir import filas_a_documentos_internos
from core.adaptadores.modelo_interno import DocumentoInterno

BOGOTA = ZoneInfo("America/Bogota")


@dataclass
class SeleccionIngesta:
    documentos: list[DocumentoInterno] = field(default_factory=list)
    ya_cargados: int = 0
    descartados: int = 0

    def resumen_por_serie(self) -> list[dict]:
        """Una fila por serie (tipo-código) con la cantidad y el rango de consecutivos."""
        series: dict[str, list[str]] = {}
        for d in self.documentos:
            series.setdefault(f"{d.tipo_comprobante}-{d.codigo_comprobante}", []).append(d.factura)
        return [
            {
                "serie": serie,
                "documentos": len(facturas),
                "desde": min(facturas, key=_orden),
                "hasta": max(facturas, key=_orden),
            }
            for serie, facturas in sorted(series.items())
        ]


def _orden(factura: str):
    return (0, int(factura)) if factura.isdigit() else (1, factura)


def _marca(desde_o_hasta: datetime) -> str:
    """Datetime -> 'YYYYMMDDHHMMSS' en hora de Bogotá, como vienen fecha+hora_actualizacion."""
    return desde_o_hasta.astimezone(BOGOTA).strftime("%Y%m%d%H%M%S")


def _filtrar_por_hora(filas, desde, hasta):
    """Misma semántica que el agente: (desde, hasta]. Sin fecha/hora no se puede ubicar la fila."""
    d = _marca(desde) if desde else None
    h = _marca(hasta) if hasta else None
    salida = []
    for f in filas:
        fecha, hora = f.get("fecha_actualizacion"), f.get("hora_actualizacion")
        if not fecha or not hora:
            continue
        marca = f"{fecha}{hora}"
        if (d and marca <= d) or (h and marca > h):
            continue
        salida.append(f)
    return salida


def _cargados_y_descartados():
    """Claves (tipo, código, factura) ya presentes en cortes válidos o eliminadas a propósito."""
    cargados = set(
        Documento.objects.exclude(corte__estado="con_error").values_list(
            "tipo_comprobante", "codigo_comprobante", "factura"
        )
    )
    descartados = set(
        DocumentoDescartado.objects.values_list(
            "tipo_comprobante", "codigo_comprobante", "factura"
        )
    )
    return cargados, descartados


def _esta_en(conjunto, doc: DocumentoInterno) -> bool:
    # Los documentos históricos no guardan el código: una clave sin código vale para cualquiera.
    return (doc.tipo_comprobante, doc.codigo_comprobante, doc.factura) in conjunto or (
        doc.tipo_comprobante,
        "",
        doc.factura,
    ) in conjunto


def seleccionar_documentos(ingestion, desde=None, hasta=None) -> SeleccionIngesta:
    """Documentos de la ingesta que todavía no están en ningún corte (ni se eliminaron a propósito)."""
    filas = ingestion.payload.get("rows", [])
    if desde or hasta:
        filas = _filtrar_por_hora(filas, desde, hasta)

    cargados, descartados = _cargados_y_descartados()
    seleccion = SeleccionIngesta()
    for doc in filas_a_documentos_internos(filas):
        if _esta_en(descartados, doc):
            seleccion.descartados += 1
        elif _esta_en(cargados, doc):
            seleccion.ya_cargados += 1
        else:
            seleccion.documentos.append(doc)
    return seleccion
