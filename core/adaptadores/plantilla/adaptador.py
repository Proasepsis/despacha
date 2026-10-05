from pathlib import Path
from decimal import Decimal

from openpyxl import load_workbook

from ..base import AdaptadorFormato
from ..modelo_interno import DocumentoInterno, LineaInterna
from ..registry import registrar

COLUMNAS_ESPERADAS = [
    "NÚMERO DE DOCUMENTO",
    "TIPO DE COMPROBANTE",
    "CÓDIGO COMPROBANTE",
    "CUENTA CONTABLE",
    "DÉBITO O CRÉDITO",
    "LÍNEA PRODUCTO",
    "GRUPO PRODUCTO",
    "CÓDIGO PRODUCTO",
    "CANTIDAD",
    "LOTE",
    "NIT",
    "CÓDIGO DE LA CIUDAD",
    "DESCRIPCIÓN DE LA SECUENCIA",
    "SUCURSAL",
]

CODIGOS_PERMITIDOS = {"F": {1}, "H": {5}, "S": {1}, "T": {10, 25}}


def _normalizar(s: str) -> str:
    return " ".join(s.upper().split())


def _buscar_columna(encabezados: list[str], esperada: str) -> int:
    """Busca una columna cuyo encabezado CONTENGA el texto esperado. Devuelve índice 1-based o 0."""
    normalizada_esp = _normalizar(esperada)
    for idx, enc in enumerate(encabezados, start=1):
        if normalizada_esp in _normalizar(enc):
            return idx
    return 0


def _a_str(valor) -> str:
    """Convierte un valor de celda a string de forma segura, preservando puntos."""
    if valor is None:
        return ""
    if isinstance(valor, float):
        return f"{valor:.6f}".rstrip("0").rstrip(".")
    return str(valor)


def _a_int_o_str(valor) -> str:
    """Convierte un valor de celda a entero string. Maneja floats (150.0 → 150)."""
    if valor is None:
        return ""
    if isinstance(valor, float):
        return str(int(valor))
    return str(valor).strip()


def _es_anio(valor) -> bool:
    try:
        return 2000 <= int(float(valor)) <= 2100
    except (TypeError, ValueError):
        return False


def _filas_traen_cucon(encabezados: list[str], filas: list[tuple]) -> bool:
    """¿Las filas de datos incluyen la celda de CUCON?

    Ancla: "AÑO DEL VENCIMIENTO DEL LOTE" siempre es un año (20xx). Se prueba en qué
    alineación (con o sin la celda CUCON) cae un año en esa columna.
    ponytail: sin encabezado CUCON o sin la columna ancla se asume "no la trae".
    """
    cucon = next(
        (i for i, e in enumerate(encabezados) if _normalizar(e).startswith("CUCON")), None
    )
    anio = _buscar_columna(encabezados, "AÑO DEL VENCIMIENTO DEL LOTE") - 1
    if cucon is None or anio <= cucon:
        return False
    muestra = filas[:200]
    # sin celda CUCON la columna del año está una posición antes que en el encabezado
    sin_celda = sum(1 for f in muestra if anio - 1 < len(f) and _es_anio(f[anio - 1]))
    con_celda = sum(1 for f in muestra if anio < len(f) and _es_anio(f[anio]))
    return con_celda > sin_celda


def _armar_codigo_producto(linea_raw, grupo_raw, codigo_raw) -> str:
    """
    Concatena LÍNEA(3) + GRUPO(4) + CÓDIGO(6) → string de 13 caracteres.
    Ejemplo: 150, 5, 5 → 1500005000005
    """
    linea = _a_int_o_str(linea_raw).strip()
    grupo = _a_int_o_str(grupo_raw).strip()
    codigo = _a_int_o_str(codigo_raw).strip()

    if not linea or not grupo or not codigo:
        raise ValueError("Código de producto incompleto: una o más partes vacías")

    try:
        int(linea)
        int(grupo)
        int(codigo)
    except (ValueError, TypeError):
        raise ValueError(
            f"Código de producto no numérico: línea={linea}, grupo={grupo}, código={codigo}"
        )

    return linea.zfill(3) + grupo.zfill(4) + codigo.zfill(6)


@registrar
class AdaptadorPlantilla(AdaptadorFormato):
    nombre = "PLANTILLA"

    def validar(self, ruta_archivo: Path) -> None:
        if not ruta_archivo.exists():
            raise ValueError(f"Archivo no encontrado: {ruta_archivo}")

        wb = load_workbook(ruta_archivo, read_only=True, data_only=True)

        if "Hoja1" not in wb.sheetnames:
            wb.close()
            raise ValueError(
                "El archivo no contiene la hoja 'Hoja1'. "
                "Estructura esperada del formato: datos en Hoja1."
            )

        ws = wb["Hoja1"]

        # iter_rows funciona aunque max_column/max_row sean None (archivos sin <dimension>)
        encabezados_leidos = []
        for row in ws.iter_rows(min_row=5, max_row=5, values_only=True):
            encabezados_leidos = [str(v).strip() if v is not None else "" for v in row]
            break

        wb.close()

        if not any(encabezados_leidos):
            raise ValueError(
                "El archivo no contiene datos en la fila 5 de 'Hoja1'. "
                "Verifique que el archivo no esté vacío."
            )

        faltantes = []
        for col_esperada in COLUMNAS_ESPERADAS:
            if _buscar_columna(encabezados_leidos, col_esperada) == 0:
                faltantes.append(col_esperada)

        if faltantes:
            raise ValueError(
                f"El archivo no tiene todas las columnas esperadas en la fila 5. "
                f"Faltan: {', '.join(faltantes)}"
            )

    def parse(self, ruta_archivo: Path) -> list[DocumentoInterno]:
        self.validar(ruta_archivo)

        wb = load_workbook(ruta_archivo, read_only=True, data_only=True)
        ws = wb["Hoja1"]

        # Leer fila 5 como encabezados usando iter_rows (funciona sin <dimension>)
        header_row = 5
        encabezados_leidos = []
        for row in ws.iter_rows(min_row=header_row, max_row=header_row, values_only=True):
            encabezados_leidos = [str(v).strip() if v is not None else "" for v in row]
            break

        if not encabezados_leidos:
            wb.close()
            return []

        filas = list(ws.iter_rows(min_row=header_row + 1, values_only=True))

        # SIIGO trae siempre el encabezado CUCON, pero según la versión las filas
        # traen la celda o no: se descarta el encabezado solo si la fila no la trae.
        if not _filas_traen_cucon(encabezados_leidos, filas):
            encabezados_leidos = [
                e for e in encabezados_leidos if not _normalizar(e).startswith("CUCON")
            ]

        col_idx: dict[str, int] = {}
        for esperada in COLUMNAS_ESPERADAS:
            idx = _buscar_columna(encabezados_leidos, esperada)
            if idx:
                col_idx[esperada] = idx

        # Agrupar líneas por documento; un mismo número puede repetirse entre tipos o códigos
        documentos: dict[tuple[str, int, str], DocumentoInterno] = {}

        def _celda(fila, nombre):
            idx = col_idx.get(nombre, 0)
            if not idx or idx > len(fila):
                return None
            return fila[idx - 1]

        anio_idx = _buscar_columna(encabezados_leidos, "AÑO DEL VENCIMIENTO DEL LOTE")
        aceptadas = con_anio = 0

        for fila in filas:
            num_doc = _a_str(_celda(fila, "NÚMERO DE DOCUMENTO"))
            if not num_doc or not num_doc.strip():
                continue

            tipo_comprobante = _a_str(_celda(fila, "TIPO DE COMPROBANTE")).strip().upper()
            codigo_comprobante = _a_str(_celda(fila, "CÓDIGO COMPROBANTE")).strip()
            cuenta_contable = _a_str(_celda(fila, "CUENTA CONTABLE")).strip()
            debito_credito = _a_str(_celda(fila, "DÉBITO O CRÉDITO")).strip().upper()
            linea_producto = _a_str(_celda(fila, "LÍNEA PRODUCTO")).strip()
            grupo_producto = _a_str(_celda(fila, "GRUPO PRODUCTO")).strip()
            codigo_producto = _a_str(_celda(fila, "CÓDIGO PRODUCTO")).strip()
            cantidad = _celda(fila, "CANTIDAD")
            lote = _a_str(_celda(fila, "LOTE"))
            nit = _a_str(_celda(fila, "NIT")).strip()
            codigo_ciudad = _a_str(_celda(fila, "CÓDIGO DE LA CIUDAD")).strip()
            descripcion = _a_str(_celda(fila, "DESCRIPCIÓN DE LA SECUENCIA")).strip()
            sucursal = _a_str(_celda(fila, "SUCURSAL")).strip()

            # Criterios de filtro
            if "TRANSPORTE" in descripcion.upper():
                continue

            if tipo_comprobante not in CODIGOS_PERMITIDOS:
                continue

            codigos_esperados = CODIGOS_PERMITIDOS[tipo_comprobante]
            try:
                codigo_int = int(float(codigo_comprobante))
            except (ValueError, TypeError):
                continue
            if codigo_int not in codigos_esperados:
                continue

            if not cuenta_contable.startswith("14"):
                continue

            # T (traslados, código 10 o 25) acepta tanto D como C; los demás solo C
            es_traslado = tipo_comprobante == "T"
            if not es_traslado and debito_credito != "C":
                continue

            aceptadas += 1
            if anio_idx and anio_idx <= len(fila) and _es_anio(fila[anio_idx - 1]):
                con_anio += 1

            cantidad_dec = Decimal("0")
            if cantidad is not None:
                try:
                    cantidad_dec = Decimal(str(cantidad))
                except Exception:
                    pass

            # producto_codigo — armar concatenando las 3 partes
            try:
                codigo_producto_final = _armar_codigo_producto(
                    linea_producto, grupo_producto, codigo_producto
                )
            except ValueError:
                codigo_producto_final = ""

            linea = LineaInterna(
                producto_codigo=codigo_producto_final,
                lote_raw=lote,
                cantidad_origen=cantidad_dec,
                descripcion_origen=descripcion,
            )

            clave = (tipo_comprobante, codigo_int, num_doc)
            if clave not in documentos:
                documentos[clave] = DocumentoInterno(
                    factura=num_doc,
                    nit=nit,
                    codigo_ciudad=codigo_ciudad,
                    tipo_comprobante=tipo_comprobante,
                    sucursal=sucursal,
                )
            documentos[clave].lineas.append(linea)

        wb.close()

        # Si las columnas están corridas, el año de vencimiento nunca cae donde toca.
        # ponytail: umbral de 5 filas para no bloquear cortes diminutos sin lote.
        if anio_idx and aceptadas >= 5 and con_anio == 0:
            raise ValueError(
                "El formato del archivo parece haber cambiado: la columna "
                "'AÑO DEL VENCIMIENTO DEL LOTE' no contiene años en ninguna fila, "
                "así que las columnas están desalineadas. Avise a soporte."
            )
        return list(documentos.values())
