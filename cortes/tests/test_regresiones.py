"""Regresiones de los hallazgos de la auditoría de fragilidad (Fase 1).

Cada test falla con el código anterior al fix correspondiente.
"""
import json
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from cortes.models import Auditoria, Corte, Documento, Linea
from cortes.servicios.cargar import cargar_archivo
from cortes.servicios.generar import generar_y_entregar
from cortes.servicios.split import deshacer_split, partir_documento
from productos.models import Ciudad, Producto


class _AdaptadorVacio:
    def validar(self, ruta):
        pass

    def parse(self, ruta):
        return []


def _usuario(nombre, grupo=None):
    user = User.objects.create_user(nombre, password="x")
    if grupo:
        user.groups.add(Group.objects.get_or_create(name=grupo)[0])
    return user


def _corte(usuario, estado="en_revision", version=0, ciudad=None):
    corte = Corte.objects.create(
        archivo="c.xlsx", hash_sha256="h" * 64, usuario_carga=usuario,
        fecha=datetime(2026, 7, 8).date(), numero_corte=1,
        estado=estado, version_actual=version,
    )
    doc = Documento.objects.create(corte=corte, factura="F1", nit="900", tipo_comprobante="F", ciudad=ciudad)
    for _ in range(2):
        Linea.objects.create(
            documento=doc, referencia="R", lote="L1", cantidad_origen=Decimal("1"),
            cantidad_unidades=1, referencia_snapshot="R", descripcion_snapshot="P",
            unidad_empaque_snapshot=1,
        )
    return corte, doc


class FechaCargaTest(TestCase):
    def test_fecha_del_corte_es_la_de_bogota_no_la_del_servidor(self):
        # 03:00 UTC del 1 de enero = 22:00 del 31 de diciembre en Bogotá
        ahora_utc = datetime(2030, 1, 1, 3, 0, tzinfo=dt_timezone.utc)
        with patch("django.utils.timezone.now", return_value=ahora_utc), \
                patch("cortes.servicios.cargar.obtener_adaptador", return_value=_AdaptadorVacio()):
            corte, _ = cargar_archivo(
                SimpleUploadedFile("x.xlsx", b"contenido"), _usuario("u"), "PLANTILLA", 1,
            )
        self.assertEqual(corte.fecha.isoformat(), "2029-12-31")


class EditarCorteTest(TestCase):
    def setUp(self):
        self.user = _usuario("editor", "almacenamiento")
        self.corte, self.doc = _corte(self.user)
        self.client.force_login(self.user)

    def _editar(self, campo, valor):
        return self.client.post(
            reverse("editar_corte", args=[self.corte.pk]),
            data=json.dumps({"tipo": "documento", "id": self.doc.pk, "campo": campo, "valor": valor}),
            content_type="application/json",
        )

    def test_campo_inexistente_es_400_no_500(self):
        self.assertEqual(self._editar("no_existe", "x").status_code, 400)

    def test_clasificador_fuera_de_las_opciones_se_rechaza(self):
        self.assertEqual(self._editar("clasificador1", "CUALQUIER COSA").status_code, 400)
        self.assertEqual(self._editar("observaciones", "OTRA").status_code, 400)
        self.doc.refresh_from_db()
        self.assertEqual((self.doc.clasificador1, self.doc.observaciones), ("EMBALAR", "PRIORIDAD"))

    def test_opcion_valida_se_guarda(self):
        self.assertEqual(self._editar("clasificador1", "NO EMBALAR").status_code, 200)


@override_settings(MEDIA_ROOT="/tmp/test_media_regresiones")
class GenerarTest(TestCase):
    def setUp(self):
        self.user = _usuario("gen", "almacenamiento")

    def test_regeneracion_fallida_no_saca_de_generado_al_corte(self):
        corte, _ = _corte(self.user, estado="generado", version=1)
        with patch.dict("os.environ", {"DRIVE_SERVICE_ACCOUNT_JSON": ""}):
            resultado = generar_y_entregar(corte, destinos=["drive"], usuario=self.user)
        self.assertFalse(resultado["success"])
        corte.refresh_from_db()
        self.assertEqual((corte.estado, corte.version_actual), ("generado", 1))

    def test_primera_generacion_fallida_queda_con_error(self):
        corte, _ = _corte(self.user)
        with patch.dict("os.environ", {"DRIVE_SERVICE_ACCOUNT_JSON": ""}):
            generar_y_entregar(corte, destinos=["drive"], usuario=self.user)
        corte.refresh_from_db()
        self.assertEqual(corte.estado, "con_error")

    def test_nombre_de_hoja_invalido_da_error_claro(self):
        ciudad = Ciudad.objects.create(codigo="X1", nombre="X", nombre_archivo="BOGOTA/NORTE")
        corte, _ = _corte(self.user, ciudad=ciudad)
        with self.assertRaisesMessage(ValueError, "BOGOTA/NORTE"):
            generar_y_entregar(corte, destinos=["descarga"], usuario=self.user)

    def test_vista_responde_400_con_nombre_de_hoja_invalido(self):
        ciudad = Ciudad.objects.create(codigo="X2", nombre="X", nombre_archivo="CALI: SUR")
        corte, _ = _corte(self.user, ciudad=ciudad)
        self.client.force_login(self.user)
        resp = self.client.post(reverse("generar_corte", args=[corte.pk]), {"destinos": ["descarga"]})
        self.assertEqual(resp.status_code, 400)


class SplitAuditoriaTest(TestCase):
    def test_deshacer_split_audita_el_id_del_documento_borrado(self):
        user = _usuario("s")
        corte, doc = _corte(user)
        nuevo = partir_documento(doc, [doc.lineas.first().pk], user)
        nuevo_pk = nuevo.pk
        deshacer_split(nuevo, user)
        evento = Auditoria.objects.get(tipo_evento="deshacer_split")
        self.assertIn(f"id={nuevo_pk}", evento.valor_anterior)


class AuditoriaProductoTest(TestCase):
    def test_cambio_de_unidad_empaque_y_activo_queda_auditado(self):
        p = Producto.objects.create(producto="1500005000005", referencia="R", descripcion="D", unidad_empaque=1)
        p.unidad_empaque = 12
        p.activo = False
        p.save()
        campos = set(
            Auditoria.objects.filter(objeto_tipo="Producto", tipo_evento="edicion").values_list("campo", flat=True)
        )
        self.assertEqual(campos, {"unidad_empaque", "activo"})


class SaludTest(TestCase):
    def test_salud_consulta_la_base_de_datos(self):
        resp = self.client.get("/salud/")
        self.assertEqual(resp.status_code, 200)
        with patch("despacha.urls.connection.cursor", side_effect=Exception("db caída")):
            self.assertEqual(self.client.get("/salud/").status_code, 503)
