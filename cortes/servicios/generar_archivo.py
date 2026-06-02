from io import BytesIO
from decimal import Decimal

import xlwt

from cortes.models import Corte
from productos.models import Ciudad
from core.models import ParametroSalida


COLUMNAS = [
    "punto", "identificacion", "nombre", "ciudad", "direccion",
    "tipo_documento_referencia", "documento_referencia", "fecha_envio",
    "hora_envio", "bodega_alistamiento", "sector_alistamiento", "area_alistamiento",
    "clasificador1", "clasificador2", "observaciones", "articulo", "lote",
    "estado_articulo", "sscc", "sscc_completo", "cantidad", "campo1", "campo2",
    "valor", "descripcion", "dato_adicional", "zona", "prioridad", "telefono",
    "email", "Proveedor",
]


def _cargar_parametros() -> dict[str, str]:
    return {
        p.clave: p.valor
        for p in ParametroSalida.objects.all()
    }


def _ciudad_archivo(documento, params: dict) -> str:
    if documento.ciudad and documento.ciudad.nombre_archivo:
        return documento.ciudad.nombre_archivo
    return params.get("ciudad_default", "")


def _cantidad_a_str(cantidad) -> str:
    if cantidad == int(cantidad):
        return str(int(cantidad))
    return f"{cantidad:.2f}"


def generar_xls(corte: Corte) -> bytes:
    params = _cargar_parametros()

    wb = xlwt.Workbook(encoding="utf-8")

    documentos = corte.documentos.select_related("ciudad").prefetch_related("lineas").all()

    ciudades: dict[str, list] = {}
    for doc in documentos:
        nombre_ciudad = _ciudad_archivo(doc, params)
        if nombre_ciudad not in ciudades:
            ciudades[nombre_ciudad] = []
        for linea in doc.lineas.all():
            ciudades[nombre_ciudad].append((doc, linea))

    for nombre_ciudad, filas in ciudades.items():
        ws = wb.add_sheet(nombre_ciudad[:31])

        for col_idx, col_name in enumerate(COLUMNAS):
            ws.write(0, col_idx, col_name)

        for row_idx, (doc, linea) in enumerate(filas, start=1):
            valores = {
                "punto": params.get("punto", ""),
                "identificacion": params.get("identificacion", ""),
                "nombre": params.get("nombre", ""),
                "ciudad": nombre_ciudad,
                "direccion": params.get("direccion", ""),
                "tipo_documento_referencia": params.get("tipo_doc_ref", ""),
                "documento_referencia": doc.factura,
                "fecha_envio": "",
                "hora_envio": "",
                "bodega_alistamiento": "",
                "sector_alistamiento": "",
                "area_alistamiento": "",
                "clasificador1": doc.clasificador1,
                "clasificador2": doc.factura,
                "observaciones": doc.observaciones,
                "articulo": linea.referencia_snapshot,
                "lote": linea.lote,
                "estado_articulo": params.get("estado_articulo", ""),
                "sscc": "",
                "sscc_completo": "",
                "cantidad": _cantidad_a_str(linea.cantidad_unidades),
                "campo1": "",
                "campo2": "",
                "valor": "",
                "descripcion": linea.descripcion_snapshot,
                "dato_adicional": "",
                "zona": "",
                "prioridad": "",
                "telefono": "",
                "email": "",
                "Proveedor": "",
            }
            for col_idx, col_name in enumerate(COLUMNAS):
                ws.write(row_idx, col_idx, valores.get(col_name, ""))

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
