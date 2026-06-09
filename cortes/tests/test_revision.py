import json
from datetime import date, timedelta
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.utils import timezone

from cortes.models import Corte, Documento, Linea, Auditoria, PresenciaCorte
from cortes.servicios.split import partir_documento, deshacer_split
from productos.models import Producto


@override_settings(MEDIA_ROOT="/tmp/test_media_rev")
class VistaRevisionTest(TestCase):
    def setUp(self):
        Path("/tmp/test_media_rev/uploads").mkdir(parents=True, exist_ok=True)

        self.almacenamiento = User.objects.create_user(username="alm1", password="test")
        self.almacenamiento2 = User.objects.create_user(username="alm2", password="test")
        self.facturacion = User.objects.create_user(username="fac1", password="test")
        self.admin = User.objects.create_user(username="adm", password="test")

        grupo_almacenamiento, _ = Group.objects.get_or_create(name="almacenamiento")
        grupo_facturacion, _ = Group.objects.get_or_create(name="facturacion")
        grupo_admin, _ = Group.objects.get_or_create(name="admin")

        self.almacenamiento.groups.add(grupo_almacenamiento)
        self.almacenamiento2.groups.add(grupo_almacenamiento)
        self.facturacion.groups.add(grupo_facturacion)
        self.admin.groups.add(grupo_admin)

        Producto.objects.create(
            producto="1500005000005",
            referencia="REF1",
            descripcion="DESC1",
            unidad_empaque=4,
            activo=True,
        )

        self.corte = Corte.objects.create(
            archivo="test.xlsx",
            hash_sha256="abc_rev",
            usuario_carga=self.almacenamiento,
            fecha=date(2026, 5, 6),
            numero_corte=2,
            estado="en_revision",
        )

        self.doc = Documento.objects.create(
            corte=self.corte,
            factura="DOC001",
            nit="800123",
            clasificador1="EMBALAR",
            observaciones="NO PRIORIDAD",
        )

        self.linea = Linea.objects.create(
            documento=self.doc,
            referencia="REF1",
            lote="15F22",
            cantidad_origen=7,
            cantidad_unidades=28,
            referencia_snapshot="REF1",
            descripcion_snapshot="DESC1",
            unidad_empaque_snapshot=4,
        )

        Linea.objects.create(
            documento=self.doc,
            referencia="REF2",
            lote="15G33",
            cantidad_origen=5,
            cantidad_unidades=20,
            referencia_snapshot="REF2",
            descripcion_snapshot="DESC2",
            unidad_empaque_snapshot=4,
        )

    def test_editar_clasificador1_autosave(self):
        self.client.login(username="alm1", password="test")

        response = self.client.post(
            reverse("editar_corte", args=[self.corte.pk]),
            json.dumps({
                "tipo": "documento",
                "id": self.doc.pk,
                "campo": "clasificador1",
                "valor": "NO EMBALAR",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.clasificador1, "NO EMBALAR")

        auditoria = Auditoria.objects.filter(objeto_tipo="Documento").first()
        self.assertIsNotNone(auditoria)
        self.assertEqual(auditoria.campo, "clasificador1")
        self.assertEqual(auditoria.tipo_evento, "edicion")

    def test_editar_cantidad_linea(self):
        self.client.login(username="alm1", password="test")

        response = self.client.post(
            reverse("editar_corte", args=[self.corte.pk]),
            json.dumps({
                "tipo": "linea",
                "id": self.linea.pk,
                "campo": "cantidad_unidades",
                "valor": "100.50",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        self.linea.refresh_from_db()
        self.assertEqual(self.linea.cantidad_unidades, 100.50)

    def test_cantidad_negativa_rechazada(self):
        self.client.login(username="alm1", password="test")

        response = self.client.post(
            reverse("editar_corte", args=[self.corte.pk]),
            json.dumps({
                "tipo": "linea",
                "id": self.linea.pk,
                "campo": "cantidad_unidades",
                "valor": "-5",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_facturacion_no_puede_editar(self):
        self.client.login(username="fac1", password="test")
        response = self.client.post(
            reverse("editar_corte", args=[self.corte.pk]),
            json.dumps({
                "tipo": "documento",
                "id": self.doc.pk,
                "campo": "clasificador1",
                "valor": "NO EMBALAR",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_almacenamiento_puede_editar_sin_lock(self):
        self.client.login(username="alm1", password="test")
        response = self.client.post(
            reverse("editar_corte", args=[self.corte.pk]),
            json.dumps({
                "tipo": "documento",
                "id": self.doc.pk,
                "campo": "clasificador1",
                "valor": "NO EMBALAR",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_forzar_liberacion_admin(self):
        # Fijamos manualmente un bloqueo legacy para probar la liberación forzada
        self.corte.bloqueado_por = self.almacenamiento
        self.corte.bloqueado_hasta = timezone.now() + timedelta(minutes=30)
        self.corte.save(update_fields=["bloqueado_por", "bloqueado_hasta"])

        self.client.login(username="adm", password="test")
        response = self.client.post(
            reverse("forzar_liberacion", args=[self.corte.pk]),
            "{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.corte.refresh_from_db()
        self.assertIsNone(self.corte.bloqueado_por)

        auditoria = Auditoria.objects.filter(tipo_evento="forzar_liberacion").first()
        self.assertIsNotNone(auditoria)

    def test_documento_campos_novedad_defaults(self):
        nuevo = Documento.objects.create(
            corte=self.corte,
            factura="NUEVO001",
            nit="999999",
            clasificador1="EMBALAR",
            observaciones="NO PRIORIDAD",
        )
        self.assertFalse(nuevo.subsanar_novedad)
        self.assertEqual(nuevo.factura_sufijo, "")

    def test_autosave_subsanar_novedad_activar(self):
        self.client.login(username="alm1", password="test")
        response = self.client.post(
            reverse("editar_corte", args=[self.corte.pk]),
            json.dumps({"tipo": "documento", "id": self.doc.pk,
                        "campo": "subsanar_novedad", "valor": "true"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.doc.refresh_from_db()
        self.assertTrue(self.doc.subsanar_novedad)

    def test_autosave_factura_sufijo_con_novedad_activa(self):
        self.client.login(username="alm1", password="test")
        self.doc.subsanar_novedad = True
        self.doc.save()
        response = self.client.post(
            reverse("editar_corte", args=[self.corte.pk]),
            json.dumps({"tipo": "documento", "id": self.doc.pk,
                        "campo": "factura_sufijo", "valor": "A"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.factura_sufijo, "A")

    def test_autosave_factura_sufijo_sin_novedad_rechazado(self):
        self.client.login(username="alm1", password="test")
        response = self.client.post(
            reverse("editar_corte", args=[self.corte.pk]),
            json.dumps({"tipo": "documento", "id": self.doc.pk,
                        "campo": "factura_sufijo", "valor": "A"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_desactivar_novedad_limpia_sufijo(self):
        self.client.login(username="alm1", password="test")
        self.doc.subsanar_novedad = True
        self.doc.factura_sufijo = "AA"
        self.doc.save()
        response = self.client.post(
            reverse("editar_corte", args=[self.corte.pk]),
            json.dumps({"tipo": "documento", "id": self.doc.pk,
                        "campo": "subsanar_novedad", "valor": "false"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.doc.refresh_from_db()
        self.assertFalse(self.doc.subsanar_novedad)
        self.assertEqual(self.doc.factura_sufijo, "")


class SplitDocumentoTest(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username="alm1", password="test")
        grupo_almacenamiento, _ = Group.objects.get_or_create(name="almacenamiento")
        self.usuario.groups.add(grupo_almacenamiento)

        self.corte = Corte.objects.create(
            archivo="test.xlsx",
            hash_sha256="abc_split",
            usuario_carga=self.usuario,
            fecha=date(2026, 5, 6),
            numero_corte=2,
            estado="en_revision",
        )

        self.doc = Documento.objects.create(
            corte=self.corte,
            factura="53725",
            nit="800000",
            clasificador1="EMBALAR",
            observaciones="NO PRIORIDAD",
        )

        self.l1 = Linea.objects.create(
            documento=self.doc,
            referencia="REF1", lote="L1",
            cantidad_origen=1, cantidad_unidades=1,
            referencia_snapshot="REF1", descripcion_snapshot="D1",
            unidad_empaque_snapshot=1,
        )
        self.l2 = Linea.objects.create(
            documento=self.doc,
            referencia="REF2", lote="L2",
            cantidad_origen=2, cantidad_unidades=2,
            referencia_snapshot="REF2", descripcion_snapshot="D2",
            unidad_empaque_snapshot=1,
        )
        self.l3 = Linea.objects.create(
            documento=self.doc,
            referencia="REF3", lote="L3",
            cantidad_origen=3, cantidad_unidades=3,
            referencia_snapshot="REF3", descripcion_snapshot="D3",
            unidad_empaque_snapshot=1,
        )
        self.l4 = Linea.objects.create(
            documento=self.doc,
            referencia="REF4", lote="L4",
            cantidad_origen=4, cantidad_unidades=4,
            referencia_snapshot="REF4", descripcion_snapshot="D4",
            unidad_empaque_snapshot=1,
        )

    def test_split_crea_nuevo_documento(self):
        nuevo = partir_documento(self.doc, [self.l1.pk, self.l2.pk], self.usuario)

        self.assertEqual(nuevo.factura, "53725A")
        self.assertEqual(nuevo.clasificador1, "EMBALAR")
        self.assertEqual(nuevo.creado_por_split_de, self.doc)
        self.assertEqual(nuevo.lineas.count(), 2)

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.lineas.count(), 2)

        self.l1.refresh_from_db()
        self.assertEqual(self.l1.documento, nuevo)
        self.assertEqual(self.l1.movida_desde, self.doc)

    def test_split_multiple_sufijos(self):
        nuevo_a = partir_documento(self.doc, [self.l1.pk], self.usuario)
        nuevo_b = partir_documento(self.doc, [self.l2.pk], self.usuario)

        self.assertEqual(nuevo_a.factura, "53725A")
        self.assertEqual(nuevo_b.factura, "53725B")

    def test_deshacer_split(self):
        nuevo = partir_documento(self.doc, [self.l1.pk, self.l2.pk], self.usuario)

        deshacer_split(nuevo, self.usuario)

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.lineas.count(), 4)

        with self.assertRaises(Documento.DoesNotExist):
            Documento.objects.get(pk=nuevo.pk)

    def test_deshacer_split_corte_generado_no_permitido(self):
        nuevo = partir_documento(self.doc, [self.l1.pk], self.usuario)

        self.corte.estado = "generado"
        self.corte.save()

        with self.assertRaises(ValueError):
            deshacer_split(nuevo, self.usuario)

    def test_generacion_bloqueada_sin_maestro(self):
        self.l1.sin_maestro = True
        self.l1.save()

        self.client.login(username="alm1", password="test")
        response = self.client.get(reverse("detalle_corte", args=[self.corte.pk]))
        self.assertContains(response, "Generar (bloqueado)")


class PresenciaPingViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alm_pres", password="test")
        grupo, _ = Group.objects.get_or_create(name="almacenamiento")
        self.user.groups.add(grupo)

        self.corte = Corte.objects.create(
            archivo="t.xlsx",
            hash_sha256="pres_xyz",
            usuario_carga=self.user,
            fecha=date(2026, 6, 9),
            numero_corte=1,
            estado="en_revision",
        )

    def test_post_crea_presencia(self):
        self.client.login(username="alm_pres", password="test")
        response = self.client.post(reverse("presencia_corte", args=[self.corte.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(PresenciaCorte.objects.filter(corte=self.corte, user=self.user).count(), 1)

    def test_get_devuelve_activos(self):
        self.client.login(username="alm_pres", password="test")
        PresenciaCorte.objects.create(
            user=self.user, corte=self.corte, visto_en=timezone.now()
        )
        response = self.client.get(reverse("presencia_corte", args=[self.corte.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["usuarios"]), 1)
        self.assertEqual(data["usuarios"][0]["username"], "alm_pres")
        self.assertTrue(data["usuarios"][0]["soy_yo"])

    def test_get_limpia_stale(self):
        self.client.login(username="alm_pres", password="test")
        old_time = timezone.now() - timedelta(seconds=30)
        PresenciaCorte.objects.create(
            user=self.user, corte=self.corte, visto_en=old_time
        )
        response = self.client.get(reverse("presencia_corte", args=[self.corte.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["usuarios"]), 0)
        self.assertEqual(PresenciaCorte.objects.filter(corte=self.corte).count(), 0)
