"""Adaptador de fuente SIIGO.

Convierte las filas crudas recibidas por el endpoint de ingesta (JSON) en
``DocumentoInterno`` aplicando exactamente las mismas reglas de alcance que el
adaptador ``PLANTILLA`` basado en XLSX. De esta forma la vía SIIGO API produce
los mismos cortes que la vía de archivo, sin duplicar lógica de negocio.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from core.adaptadores.modelo_interno import DocumentoInterno, LineaInterna

CODIGOS_PERMITIDOS = {"F": {1}, "H": {5}, "S": {1}, "T": {10, 25}}

BODEGA_VIGIA = 400
UBICACION_VIGIA = 5


def _txt(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, float):
        if valor.is_integer():
            return str(int(valor))
        return f"{valor:.6f}".rstrip("0").rstrip(".")
    return str(valor)


def _armar_codigo_producto(linea, grupo, codigo) -> str:
    linea = _txt(linea).strip()
    grupo = _txt(grupo).strip()
    codigo = _txt(codigo).strip()
    if not linea or not grupo or not codigo:
        return ""
    try:
        int(linea)
        int(grupo)
        int(codigo)
    except (ValueError, TypeError):
        return ""
    return linea.zfill(3) + grupo.zfill(4) + codigo.zfill(6)


def _es_movimiento_vigia(fila) -> bool:
    """Conserva solo bodega 400 y ubicación 5, comparadas como enteros."""
    try:
        bodega = int(str(fila.get("codigo_bodega") or "").strip())
        ubicacion = int(str(fila.get("codigo_ubicacion") or "").strip())
    except (ValueError, TypeError):
        return False
    return bodega == BODEGA_VIGIA and ubicacion == UBICACION_VIGIA


def filas_a_documentos_internos(filas: list[dict]) -> list[DocumentoInterno]:
    """Convierte filas crudas SIIGO en el modelo interno de Despacha.

    Reglas (``AdaptadorPlantilla.parse`` más el recorte de Vigía):
    1. Excluye líneas cuya descripción contenga "TRANSPORTE".
    2. Solo comprobantes permitidos por tipo (F/H/S=1, T={10,25}).
    3. La cuenta contable debe empezar por "14".
    4. Los traslados (T) aceptan D y C; los demás solo C.
    5. Solo bodega 400 Y ubicación 5 (comparadas como enteros).
    6. Producto reconstruido como línea(3)+grupo(4)+código(6).
    """
    documentos: dict[str, DocumentoInterno] = {}

    for fila in filas:
        descripcion_orig = _txt(fila.get("descripcion_secuencia")).strip()
        if "TRANSPORTE" in descripcion_orig.upper():
            continue

        tipo = _txt(fila.get("tipo_comprobante")).strip().upper()
        if tipo not in CODIGOS_PERMITIDOS:
            continue

        codigo = _txt(fila.get("codigo_comprobante")).strip()
        try:
            codigo_int = int(float(codigo))
        except (ValueError, TypeError):
            continue
        if codigo_int not in CODIGOS_PERMITIDOS[tipo]:
            continue

        cuenta = _txt(fila.get("cuenta_contable")).strip()
        if not cuenta.startswith("14"):
            continue

        debito_credito = _txt(fila.get("debito_credito")).strip().upper()
        es_traslado = tipo == "T"
        if not es_traslado and debito_credito != "C":
            continue

        if not _es_movimiento_vigia(fila):
            continue

        cantidad = fila.get("cantidad")
        try:
            cantidad_dec = (
                Decimal("0") if cantidad is None else Decimal(str(cantidad))
            )
        except (InvalidOperation, TypeError, ValueError):
            cantidad_dec = Decimal("0")

        codigo_producto_final = _armar_codigo_producto(
            fila.get("linea_producto"),
            fila.get("grupo_producto"),
            fila.get("codigo_producto"),
        )

        num_doc = _txt(fila.get("numero_documento")).strip()
        if not num_doc:
            continue

        linea = LineaInterna(
            producto_codigo=codigo_producto_final,
            lote_raw=_txt(fila.get("lote")),
            cantidad_origen=cantidad_dec,
            descripcion_origen=descripcion_orig,
        )

        if num_doc not in documentos:
            documentos[num_doc] = DocumentoInterno(
                factura=num_doc,
                nit=_txt(fila.get("nit")).strip(),
                codigo_ciudad=_txt(fila.get("codigo_ciudad")).strip(),
                tipo_comprobante=tipo,
                sucursal=_txt(fila.get("sucursal")).strip(),
            )
        documentos[num_doc].lineas.append(linea)

    return list(documentos.values())
