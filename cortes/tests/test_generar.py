import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User, Group
import xlrd

from cortes.models import Corte, Documento, Linea, CorteVersion, Auditoria
from cortes.servicios.generar_archivo import generar_xls, COLUMNAS
from cortes.servicios.nombrado import nombre_archivo_corte
from cortes.servicios.generar import generar_y_entregar
from productos.models import Producto
from core.models import ParametroSalida


@override_settings(MEDIA_ROOT="/tmp/test_media_gen")
class GenerarArchivoTest(TestCase):
    def setUp(self):
        Path("/tmp/test_media_gen/uploads").mkdir(parents=True, exist_ok=True)

        self.usuario = User.objects.create_user(username="op1", password="test")
        grupo, _ = Group.objects.get_or_create(name="operario")
        self.usuario.groups.add(grupo)

        self.corte = Corte.objects.create(
            archivo="test.xlsx",
            hash_sha256="abc_gen",
            usuario_carga=self.usuario,
            fecha=date(2026, 5, 5),
            numero_corte=1,
            estado="en_revision",
        )

        Producto.objects.create(
            producto="1500005000005",
            referencia="REF1",
            descripcion="PRODUCTO DE PRUEBA",
            unidad_empaque=4,
            activo=True,
        )

        self.doc = Documento.objects.create(
            corte=self.corte,
            factura="FC001",
            nit="800123",
            clasificador1="EMBALAR",
            observaciones="NO PRIORIDAD",
        )

        Linea.objects.create(
            documento=self.doc,
            referencia="REF1",
            lote="121570226",
            cantidad_origen=Decimal("7"),
            cantidad_unidades=Decimal("28"),
            referencia_snapshot="REF1",
            descripcion_snapshot="PRODUCTO DE PRUEBA",
            unidad_empaque_snapshot=4,
        )

        Linea.objects.create(
            documento=self.doc,
            referencia="REF2",
            lote="15F22",
            cantidad_origen=Decimal("2"),
            cantidad_unidades=Decimal("50"),
            referencia_snapshot="REF2",
            descripcion_snapshot="OTRO PRODUCTO",
            unidad_empaque_snapshot=25,
        )

        for clave, valor in [
            ("punto", "PROA"),
            ("identificacion", "PROASEPSIS"),
            ("nombre", "PROASEPSIS"),
            ("direccion", "BOGOTA"),
            ("tipo_doc_ref", "FACT"),
            ("estado_articulo", "DISP"),
            ("ciudad_default", "BOGOTA"),
        ]:
            ParametroSalida.objects.get_or_create(clave=clave, defaults={"valor": valor})

    def test_generar_xls_31_columnas(self):
        xls_bytes = generar_xls(self.corte)
        ruta = Path("/tmp/test_gen_cols.xls")
        ruta.write_bytes(xls_bytes)

        wb = xlrd.open_workbook(str(ruta))
        ws = wb.sheet_by_name("BOGOTA")
        self.assertEqual(ws.ncols, 31)

        headers = [ws.cell_value(0, c) for c in range(31)]
        self.assertEqual(headers, COLUMNAS)
        ruta.unlink(missing_ok=True)

    def test_generar_xls_valores_correctos(self):
        xls_bytes = generar_xls(self.corte)
        ruta = Path("/tmp/test_gen_vals.xls")
        ruta.write_bytes(xls_bytes)

        wb = xlrd.open_workbook(str(ruta))
        ws = wb.sheet_by_name("BOGOTA")
        self.assertEqual(ws.nrows, 3)  # header + 2 lineas

        col_map = {}
        for c in range(31):
            col_map[ws.cell_value(0, c)] = c

        self.assertEqual(ws.cell_value(1, col_map["punto"]), "PROA")
        self.assertEqual(ws.cell_value(1, col_map["articulo"]), "REF1")
        self.assertEqual(ws.cell_value(1, col_map["lote"]), "121570226")

        cantidad = ws.cell_value(1, col_map["cantidad"])
        self.assertEqual(str(cantidad).rstrip("0").rstrip("."), "28")

        self.assertEqual(ws.cell_value(1, col_map["documento_referencia"]), "FC001")
        self.assertEqual(ws.cell_value(1, col_map["clasificador2"]), "FC001")
        self.assertEqual(ws.cell_value(1, col_map["clasificador1"]), "EMBALAR")

        self.assertEqual(ws.cell_value(2, col_map["articulo"]), "REF2")

        ruta.unlink(missing_ok=True)

    def test_nombrado_sin_version(self):
        nombre = nombre_archivo_corte(self.corte, siguiente_version=1)
        self.assertEqual(nombre, "MAY 5 corte 1.xls")

    def test_nombrado_con_version(self):
        nombre = nombre_archivo_corte(self.corte, siguiente_version=3)
        self.assertEqual(nombre, "MAY 5 corte 1 (v3).xls")

    def test_generar_descarga_exitoso(self):
        resultado = generar_y_entregar(
            self.corte,
            destinos=["descarga"],
            usuario=self.usuario,
        )

        self.assertTrue(resultado["success"])
        self.assertEqual(resultado["version"], 1)
        self.assertGreater(len(resultado["archivo_bytes"]), 0)
        self.assertEqual(resultado["nombre_archivo"], "MAY 5 corte 1.xls")

        self.corte.refresh_from_db()
        self.assertEqual(self.corte.estado, "generado")
        self.assertEqual(self.corte.version_actual, 1)

        version = CorteVersion.objects.get(corte=self.corte)
        self.assertEqual(version.numero, 1)
        self.assertEqual(version.usuario, self.usuario)

    def test_generar_sin_maestro_rechaza(self):
        self.corte.documentos.first().lineas.update(sin_maestro=True)

        with self.assertRaises(ValueError) as ctx:
            generar_y_entregar(self.corte, destinos=["descarga"], usuario=self.usuario)

        self.assertIn("sin producto en la maestra", str(ctx.exception))

    def test_generar_destinos_vacios_rechaza(self):
        with self.assertRaises(ValueError) as ctx:
            generar_y_entregar(self.corte, destinos=[], usuario=self.usuario)

        self.assertIn("al menos un destino", str(ctx.exception))


@override_settings(MEDIA_ROOT="/tmp/test_media_gen2")
class GenerarRegeneracionTest(TestCase):
    def setUp(self):
        Path("/tmp/test_media_gen2/uploads").mkdir(parents=True, exist_ok=True)

        self.usuario = User.objects.create_user(username="op1", password="test")
        grupo, _ = Group.objects.get_or_create(name="operario")
        self.usuario.groups.add(grupo)

        self.corte = Corte.objects.create(
            archivo="test.xlsx",
            hash_sha256="abc_reg",
            usuario_carga=self.usuario,
            fecha=date(2026, 5, 5),
            numero_corte=1,
            estado="en_revision",
        )

        Producto.objects.create(
            producto="1500005000005",
            referencia="REF1",
            descripcion="DESC1",
            unidad_empaque=4,
            activo=True,
        )

        doc = Documento.objects.create(
            corte=self.corte,
            factura="FC001",
        )
        Linea.objects.create(
            documento=doc,
            referencia="REF1",
            lote="L1",
            cantidad_origen=1, cantidad_unidades=4,
            referencia_snapshot="REF1",
            descripcion_snapshot="DESC1",
            unidad_empaque_snapshot=4,
        )

        for clave, valor in [
            ("punto", "PROA"), ("identificacion", "PROASEPSIS"),
            ("nombre", "PROASEPSIS"), ("direccion", "BOGOTA"),
            ("tipo_doc_ref", "FACT"), ("estado_articulo", "DISP"),
            ("ciudad_default", "BOGOTA"),
        ]:
            ParametroSalida.objects.get_or_create(clave=clave, defaults={"valor": valor})

    def test_regenerar_version_2(self):
        resultado = generar_y_entregar(
            self.corte, destinos=["descarga"], usuario=self.usuario,
        )
        self.assertEqual(resultado["version"], 1)

        resultado2 = generar_y_entregar(
            self.corte, destinos=["descarga"], usuario=self.usuario,
            motivo="Corrección de cantidades",
        )
        self.assertTrue(resultado2["success"])
        self.assertEqual(resultado2["version"], 2)
        self.assertEqual(resultado2["nombre_archivo"], "MAY 5 corte 1 (v2).xls")

        self.corte.refresh_from_db()
        self.assertEqual(self.corte.version_actual, 2)
        self.assertEqual(self.corte.estado, "generado")
        self.assertEqual(CorteVersion.objects.count(), 2)

        auditoria = Auditoria.objects.filter(tipo_evento="regeneracion").first()
        self.assertIsNotNone(auditoria)

    @patch("core.adaptadores.destinos.drive.build")
    def test_generar_drive_falla(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.files.return_value.create.side_effect = Exception("Fallo de red")

        resultado = generar_y_entregar(
            self.corte,
            destinos=["drive"],
            usuario=self.usuario,
        )

        self.assertFalse(resultado["success"])
        self.assertIn("drive", resultado["errores"][0])

        self.corte.refresh_from_db()
        self.assertEqual(self.corte.estado, "con_error")
        self.assertEqual(self.corte.version_actual, 0)


@override_settings(MEDIA_ROOT="/tmp/test_media_gen3")
class VistaGenerarTest(TestCase):
    def setUp(self):
        Path("/tmp/test_media_gen3/uploads").mkdir(parents=True, exist_ok=True)

        self.usuario = User.objects.create_user(username="op1", password="test")
        grupo, _ = Group.objects.get_or_create(name="operario")
        self.usuario.groups.add(grupo)

        self.corte = Corte.objects.create(
            archivo="test.xlsx",
            hash_sha256="abc_vgen",
            usuario_carga=self.usuario,
            fecha=date(2026, 5, 5),
            numero_corte=1,
            estado="en_revision",
        )

        Producto.objects.create(
            producto="1500005000005",
            referencia="REF1",
            descripcion="DESC1",
            unidad_empaque=4,
            activo=True,
        )

        doc = Documento.objects.create(corte=self.corte, factura="FC001")
        Linea.objects.create(
            documento=doc,
            referencia="REF1", lote="L1",
            cantidad_origen=1, cantidad_unidades=4,
            referencia_snapshot="REF1",
            descripcion_snapshot="DESC1",
            unidad_empaque_snapshot=4,
        )

        for clave, valor in [
            ("punto", "PROA"), ("identificacion", "PROASEPSIS"),
            ("nombre", "PROASEPSIS"), ("direccion", "BOGOTA"),
            ("tipo_doc_ref", "FACT"), ("estado_articulo", "DISP"),
            ("ciudad_default", "BOGOTA"),
        ]:
            ParametroSalida.objects.get_or_create(clave=clave, defaults={"valor": valor})

    def test_vista_generar_descarga_devuelve_xls(self):
        self.client.login(username="op1", password="test")
        self.corte.bloqueado_por = self.usuario
        from django.utils import timezone
        self.corte.bloqueado_hasta = timezone.now() + timezone.timedelta(minutes=30)
        self.corte.save()

        response = self.client.post(
            reverse("generar_corte", args=[self.corte.pk]),
            {"destinos": ["descarga"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.ms-excel")
        self.assertIn("attachment", response["Content-Disposition"])
