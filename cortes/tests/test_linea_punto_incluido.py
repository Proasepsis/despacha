from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth.models import User
from cortes.models import Corte, Documento, Linea


class LineaPuntoIncluidoTest(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username="op1", password="test")
        self.corte = Corte.objects.create(
            archivo="test.xlsx",
            hash_sha256="abc_punto",
            usuario_carga=self.usuario,
            fecha=date(2026, 5, 5),
            numero_corte=1,
            estado="en_revision",
        )
        self.doc = Documento.objects.create(
            corte=self.corte,
            factura="FC001",
            nit="800123",
            clasificador1="EMBALAR",
            observaciones="NO PRIORIDAD",
        )

    def _crear_linea(self, lote):
        return Linea.objects.create(
            documento=self.doc,
            referencia="REF1",
            lote=lote,
            cantidad_origen=Decimal("1"),
            cantidad_unidades=1,
            referencia_snapshot="REF1",
            descripcion_snapshot="DESC1",
            unidad_empaque_snapshot=1,
        )

    def test_punto_incluido_default_false(self):
        linea = self._crear_linea("120010925.")
        self.assertFalse(linea.punto_incluido)

    def test_tiene_punto_final_true(self):
        linea = self._crear_linea("120010925.")
        self.assertTrue(linea.tiene_punto_final)

    def test_tiene_punto_final_false(self):
        linea = self._crear_linea("15F22")
        self.assertFalse(linea.tiene_punto_final)
