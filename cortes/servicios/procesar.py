from dataclasses import dataclass, field
from typing import Optional

from django.db import transaction

from productos.models import Producto, Ciudad
from cortes.models import Corte, Documento, Linea
from core.adaptadores.modelo_interno import DocumentoInterno, LineaInterna
from core.adaptadores.plantilla.limpieza import limpiar_lote


@dataclass
class ResultadoProcesamiento:
    corte: Corte
    documentos_creados: int = 0
    lineas_creadas: int = 0
    lineas_sin_maestro: int = 0
    lineas_inactivas: int = 0
    productos_nuevos_detectados: list[str] = field(default_factory=list)


@transaction.atomic
def procesar_documentos_internos(
    corte: Corte,
    documentos: list[DocumentoInterno],
) -> ResultadoProcesamiento:
    codigos_producto = set()
    for doc in documentos:
        for linea in doc.lineas:
            if linea.producto_codigo:
                codigos_producto.add(linea.producto_codigo)

    productos_map: dict[str, Producto] = {}
    if codigos_producto:
        productos_map = {
            p.producto: p
            for p in Producto.objects.filter(producto__in=codigos_producto)
        }

    codigos_ciudad = {d.codigo_ciudad for d in documentos if d.codigo_ciudad}
    ciudades_map: dict[str, Ciudad] = {}
    if codigos_ciudad:
        ciudades_map = {
            c.codigo: c
            for c in Ciudad.objects.filter(codigo__in=codigos_ciudad)
        }

    resultado = ResultadoProcesamiento(corte=corte)
    productos_nuevos_set: set[str] = set()

    documentos_a_crear: list[Documento] = []
    lineas_a_crear: list[Linea] = []
    documento_map: dict[tuple, Documento] = {}

    for doc_interno in documentos:
        ciudad = ciudades_map.get(doc_interno.codigo_ciudad)

        doc = Documento(
            corte=corte,
            factura=doc_interno.factura,
            nit=doc_interno.nit[:20],
            tipo_comprobante=doc_interno.tipo_comprobante,
            ciudad=ciudad,
        )
        documentos_a_crear.append(doc)
        documento_map[(corte.id, doc_interno.factura)] = doc

    Documento.objects.bulk_create(documentos_a_crear)

    for doc_interno in documentos:
        doc = documento_map[(corte.id, doc_interno.factura)]

        for linea_interna in doc_interno.lineas:
            codigo = linea_interna.producto_codigo
            producto = productos_map.get(codigo)

            if producto is None:
                linea = _crear_linea_sin_maestro(doc, linea_interna)
                resultado.lineas_sin_maestro += 1
                if codigo:
                    productos_nuevos_set.add(codigo)
            elif not producto.activo:
                linea = _crear_linea_con_producto(doc, linea_interna, producto)
                linea.inactivo = True
                resultado.lineas_inactivas += 1
            else:
                linea = _crear_linea_con_producto(doc, linea_interna, producto)

            lineas_a_crear.append(linea)

    Linea.objects.bulk_create(lineas_a_crear)

    resultado.documentos_creados = len(documentos)
    resultado.lineas_creadas = len(lineas_a_crear)
    resultado.productos_nuevos_detectados = sorted(productos_nuevos_set)

    return resultado


def _crear_linea_con_producto(
    doc: Documento, linea: LineaInterna, producto: Producto
) -> Linea:
    return Linea(
        documento=doc,
        referencia=producto.referencia,
        lote=limpiar_lote(linea.lote_raw),
        cantidad_origen=linea.cantidad_origen,
        cantidad_unidades=round(linea.cantidad_origen * producto.unidad_empaque),
        sin_maestro=False,
        inactivo=False,
        referencia_snapshot=producto.referencia,
        descripcion_snapshot=producto.descripcion,
        unidad_empaque_snapshot=producto.unidad_empaque,
    )


def _crear_linea_sin_maestro(doc: Documento, linea: LineaInterna) -> Linea:
    desc = linea.descripcion_origen.strip()
    if desc and len(desc) > 3:
        descripcion_snapshot = f"(sin maestra) {desc}"
    else:
        descripcion_snapshot = "(producto sin maestra)"

    return Linea(
        documento=doc,
        referencia="",
        lote=limpiar_lote(linea.lote_raw),
        cantidad_origen=linea.cantidad_origen,
        cantidad_unidades=round(linea.cantidad_origen),
        sin_maestro=True,
        inactivo=False,
        referencia_snapshot="",
        descripcion_snapshot=descripcion_snapshot,
        unidad_empaque_snapshot=1,
    )
