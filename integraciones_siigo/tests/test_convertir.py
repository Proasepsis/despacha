from django.test import SimpleTestCase

from core.adaptadores.api_siigo.convertir import filas_a_documentos_internos


def _fila(**overrides):
    fila = {
        "tipo_comprobante": "F",
        "codigo_comprobante": "001",
        "numero_documento": "56321",
        "cuenta_contable": "1430462000",
        "debito_credito": "C",
        "valor_secuencia": 1000,
        "comprobante_anulado": "N",
        "linea_producto": "165",
        "grupo_producto": "0015",
        "codigo_producto": "000025",
        "cantidad": 16,
        "codigo_bodega": "0400",
        "codigo_ubicacion": "005",
        "lote": "'120831225 ",
        "nit": "830007355",
        "codigo_ciudad": "0001",
        "descripcion_secuencia": "ASEPTIGERM JAB ANTIB ESP",
        "sucursal": "0",
    }
    fila.update(overrides)
    return fila


class ConvertirTests(SimpleTestCase):
    def test_construye_documento_y_producto(self):
        documentos = filas_a_documentos_internos([_fila()])
        self.assertEqual(len(documentos), 1)
        doc = documentos[0]
        self.assertEqual(doc.factura, "56321")
        self.assertEqual(doc.nit, "830007355")
        self.assertEqual(doc.tipo_comprobante, "F")
        self.assertEqual(len(doc.lineas), 1)
        self.assertEqual(doc.lineas[0].producto_codigo, "1650015000025")
        self.assertEqual(doc.lineas[0].lote_raw, "'120831225 ")
        self.assertEqual(str(doc.lineas[0].cantidad_origen), "16")

    def test_excluye_transporte(self):
        fila = _fila(descripcion_secuencia="SERVICIO DE TRANSPORTE NACIONAL")
        self.assertEqual(filas_a_documentos_internos([fila]), [])

    def test_excluye_tipo_no_permitido(self):
        self.assertEqual(filas_a_documentos_internos([_fila(tipo_comprobante="C")]), [])
        self.assertEqual(filas_a_documentos_internos([_fila(tipo_comprobante="D")]), [])

    def test_excluye_codigo_comprobante_no_permitido(self):
        self.assertEqual(
            filas_a_documentos_internos([_fila(codigo_comprobante="002")]), []
        )

    def test_excluye_cuenta_que_no_empieza_por_14(self):
        self.assertEqual(
            filas_a_documentos_internos([_fila(cuenta_contable="4120462005")]), []
        )

    def test_no_traslado_requiere_credito(self):
        self.assertEqual(filas_a_documentos_internos([_fila(debito_credito="D")]), [])

    def test_traslado_acepta_debito(self):
        fila = _fila(tipo_comprobante="T", codigo_comprobante="010", debito_credito="D")
        documentos = filas_a_documentos_internos([fila])
        self.assertEqual(len(documentos), 1)

    def test_agrupa_por_numero_de_documento(self):
        filas = [
            _fila(),
            _fila(codigo_producto="000030", grupo_producto="0015"),
        ]
        documentos = filas_a_documentos_internos(filas)
        self.assertEqual(len(documentos), 1)
        self.assertEqual(len(documentos[0].lineas), 2)

    def test_partes_vacias_dan_producto_vacio(self):
        fila = _fila(
            linea_producto="   ", grupo_producto="    ", codigo_producto="      "
        )
        documentos = filas_a_documentos_internos([fila])
        self.assertEqual(documentos[0].lineas[0].producto_codigo, "")

    def test_excluye_bodega_distinta_de_400(self):
        self.assertEqual(
            filas_a_documentos_internos([_fila(codigo_bodega="0215")]), []
        )

    def test_excluye_bodega_400_con_ubicacion_distinta_de_5(self):
        self.assertEqual(
            filas_a_documentos_internos([_fila(codigo_ubicacion="010")]), []
        )

    def test_acepta_bodega_y_ubicacion_como_enteros(self):
        fila = _fila(codigo_bodega=400, codigo_ubicacion=5)
        documentos = filas_a_documentos_internos([fila])
        self.assertEqual(len(documentos), 1)

    def test_excluye_bodega_vacia(self):
        self.assertEqual(
            filas_a_documentos_internos([_fila(codigo_bodega=None)]), []
        )
