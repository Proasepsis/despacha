from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.contrib.auth.models import User

from productos.models import Producto
from cortes.models import Corte, Linea
from core.adaptadores.modelo_interno import DocumentoInterno, LineaInterna
from cortes.servicios.procesar import procesar_documentos_internos


class ProcesarDocumentosTest(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username="operario1", password="test")
        self.producto_base = Producto.objects.create(
            producto="1500005000005",
            referencia="REF1",
            descripcion="DESC1",
            unidad_empaque=4,
            activo=True,
        )
        self.corte = Corte.objects.create(
            archivo="test.xlsx",
            hash_sha256="abc123",
            usuario_carga=self.usuario,
            fecha=date(2026, 5, 6),
            numero_corte=2,
            estado="cargado",
        )

    def _doc_interno(self, factura="DOC001", producto_codigo="1500005000005",
                     cantidad="7", lote="15F22"):
        linea = LineaInterna(
            producto_codigo=producto_codigo,
            lote_raw=lote,
            cantidad_origen=Decimal(cantidad),
            descripcion_origen="Descripción de prueba",
        )
        return DocumentoInterno(
            factura=factura,
            nit="800000",
            codigo_ciudad="11001",
            lineas=[linea],
        )

    def test_resolucion_producto_activo(self):
        resultado = procesar_documentos_internos(self.corte, [self._doc_interno()])

        self.assertEqual(resultado.documentos_creados, 1)
        self.assertEqual(resultado.lineas_creadas, 1)
        self.assertEqual(resultado.lineas_sin_maestro, 0)
        self.assertEqual(resultado.lineas_inactivas, 0)

        linea = Linea.objects.first()
        self.assertEqual(linea.referencia_snapshot, "REF1")
        self.assertEqual(linea.unidad_empaque_snapshot, 4)
        self.assertEqual(linea.cantidad_unidades, Decimal("28"))
        self.assertFalse(linea.sin_maestro)
        self.assertFalse(linea.inactivo)

    def test_producto_inactivo(self):
        self.producto_base.activo = False
        self.producto_base.save()

        resultado = procesar_documentos_internos(self.corte, [self._doc_interno()])

        self.assertEqual(resultado.lineas_inactivas, 1)
        linea = Linea.objects.first()
        self.assertTrue(linea.inactivo)
        self.assertFalse(linea.sin_maestro)
        self.assertEqual(linea.cantidad_unidades, Decimal("28"))

    def test_producto_sin_maestro(self):
        doc = self._doc_interno(producto_codigo="ZZZ9999999999")

        resultado = procesar_documentos_internos(self.corte, [doc])

        self.assertEqual(resultado.lineas_sin_maestro, 1)
        self.assertIn("ZZZ9999999999", resultado.productos_nuevos_detectados)

        linea = Linea.objects.first()
        self.assertTrue(linea.sin_maestro)
        self.assertFalse(linea.inactivo)
        self.assertEqual(linea.referencia_snapshot, "")
        self.assertIn("sin maestra", linea.descripcion_snapshot)
        self.assertEqual(linea.cantidad_unidades, Decimal("7"))

    def test_producto_sin_maestro_con_descripcion(self):
        doc = self._doc_interno(
            producto_codigo="ZZZ9999999999",
            cantidad="3",
        )
        doc.lineas[0].descripcion_origen = "PRODUCTO X MUY LARGO"

        resultado = procesar_documentos_internos(self.corte, [doc])

        linea = Linea.objects.first()
        self.assertIn("PRODUCTO X MUY LARGO", linea.descripcion_snapshot)
        self.assertIn("sin maestra", linea.descripcion_snapshot)

    def test_inmutabilidad_snapshot(self):
        procesar_documentos_internos(self.corte, [self._doc_interno()])

        self.producto_base.unidad_empaque = 8
        self.producto_base.referencia = "REF_MODIFICADA"
        self.producto_base.save()

        linea = Linea.objects.first()
        self.assertEqual(linea.unidad_empaque_snapshot, 4)
        self.assertEqual(linea.referencia_snapshot, "REF1")

    def test_conversion_autoritativa_7x4_28(self):
        procesar_documentos_internos(self.corte, [self._doc_interno(cantidad="7")])
        self.assertEqual(Linea.objects.first().cantidad_unidades, Decimal("28"))

    def test_conversion_autoritativa_2x25_50(self):
        Producto.objects.create(
            producto="1510010000010",
            referencia="REF2",
            descripcion="DESC2",
            unidad_empaque=25,
            activo=True,
        )
        doc = self._doc_interno(producto_codigo="1510010000010", cantidad="2")
        procesar_documentos_internos(self.corte, [doc])
        self.assertEqual(Linea.objects.first().cantidad_unidades, Decimal("50"))

    def test_conversion_autoritativa_56x1_56(self):
        Producto.objects.create(
            producto="1520015000015",
            referencia="REF3",
            descripcion="DESC3",
            unidad_empaque=1,
            activo=True,
        )
        doc = self._doc_interno(producto_codigo="1520015000015", cantidad="56")
        procesar_documentos_internos(self.corte, [doc])
        self.assertEqual(Linea.objects.first().cantidad_unidades, Decimal("56"))

    def test_productos_nuevos_detectados(self):
        doc = self._doc_interno(producto_codigo="NUEVO1234567890")
        resultado = procesar_documentos_internos(self.corte, [doc])
        self.assertIn("NUEVO1234567890", resultado.productos_nuevos_detectados)

    def test_codigo_producto_vacio_se_trata_como_sin_maestro(self):
        linea = LineaInterna(
            producto_codigo="",
            lote_raw="L123",
            cantidad_origen=Decimal("5"),
        )
        doc = DocumentoInterno(factura="DOC001", lineas=[linea])

        resultado = procesar_documentos_internos(self.corte, [doc])
        self.assertEqual(resultado.lineas_sin_maestro, 1)

    def test_lote_se_limpia_al_procesar(self):
        doc = self._doc_interno(lote="'15F22/2579")
        procesar_documentos_internos(self.corte, [doc])
        linea = Linea.objects.first()
        self.assertEqual(linea.lote, "15F22")

    def test_producto_codigo_no_numerico_tratado_como_sin_maestro(self):
        linea = LineaInterna(
            producto_codigo="ABC123",
            lote_raw="L1",
            cantidad_origen=Decimal("2"),
        )
        doc = DocumentoInterno(factura="DOC002", lineas=[linea])

        resultado = procesar_documentos_internos(self.corte, [doc])
        self.assertEqual(resultado.lineas_sin_maestro, 1)
