import json
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from cortes.models import Auditoria, Corte, Documento, Linea


class EliminarDocumentosTest(TestCase):
    def setUp(self):
        self.facturacion = User.objects.create_user(username="fac", password="x")
        self.facturacion.groups.add(Group.objects.get_or_create(name="facturacion")[0])
        self.almacenamiento = User.objects.create_user(username="alm", password="x")
        self.almacenamiento.groups.add(Group.objects.get_or_create(name="almacenamiento")[0])

        self.corte = Corte.objects.create(
            archivo="t.xlsx", hash_sha256="h", usuario_carga=self.facturacion,
            fecha=date(2026, 9, 24), numero_corte=2, estado="en_revision",
        )
        self.docs = []
        for factura in ("56570", "603", "6255"):
            doc = Documento.objects.create(corte=self.corte, factura=factura)
            Linea.objects.create(
                documento=doc, referencia="R", lote="L", cantidad_origen=1, cantidad_unidades=1,
                referencia_snapshot="R", descripcion_snapshot="D", unidad_empaque_snapshot=1,
            )
            self.docs.append(doc)
        self.url = reverse("eliminar_documentos", args=[self.corte.pk])

    def _post(self, ids):
        return self.client.post(self.url, json.dumps({"documento_ids": ids}), content_type="application/json")

    def test_facturacion_elimina_varios_con_sus_lineas_y_auditoria(self):
        self.client.force_login(self.facturacion)
        r = self._post([self.docs[1].pk, self.docs[2].pk])

        self.assertEqual(r.status_code, 200)
        self.assertEqual(list(self.corte.documentos.values_list("factura", flat=True)), ["56570"])
        self.assertEqual(Linea.objects.filter(documento__corte=self.corte).count(), 1)
        self.assertEqual(Auditoria.objects.filter(tipo_evento="eliminacion").count(), 2)

    def test_almacenamiento_no_puede_eliminar(self):
        self.client.force_login(self.almacenamiento)
        self.assertEqual(self._post([self.docs[0].pk]).status_code, 403)
        self.assertEqual(self.corte.documentos.count(), 3)

    def test_no_elimina_si_corte_generado(self):
        self.corte.estado = "generado"
        self.corte.save()
        self.client.force_login(self.facturacion)
        self.assertEqual(self._post([self.docs[0].pk]).status_code, 400)
        self.assertEqual(self.corte.documentos.count(), 3)

    def test_documento_de_otro_corte_no_se_elimina(self):
        otro = Corte.objects.create(
            archivo="o.xlsx", hash_sha256="h2", usuario_carga=self.facturacion,
            fecha=date(2026, 9, 24), numero_corte=1, estado="en_revision",
        )
        ajeno = Documento.objects.create(corte=otro, factura="999")
        self.client.force_login(self.facturacion)
        self.assertEqual(self._post([self.docs[0].pk, ajeno.pk]).status_code, 404)
        self.assertTrue(Documento.objects.filter(pk=ajeno.pk).exists())
        self.assertEqual(self.corte.documentos.count(), 3)

    def test_detalle_muestra_controles_solo_a_quien_puede_eliminar(self):
        detalle = reverse("detalle_corte", args=[self.corte.pk])
        self.client.force_login(self.facturacion)
        self.assertContains(self.client.get(detalle), 'class="sel-eliminar"')
        self.client.force_login(self.almacenamiento)
        self.assertNotContains(self.client.get(detalle), 'class="sel-eliminar"')


class AvisoYaSubidoTest(TestCase):
    def test_detalle_avisa_documento_ya_subido_en_otro_corte(self):
        user = User.objects.create_user(username="u", password="x")
        c1 = Corte.objects.create(archivo="a", hash_sha256="a", usuario_carga=user,
                                  fecha=date(2026, 9, 23), numero_corte=1, estado="generado")
        c2 = Corte.objects.create(archivo="b", hash_sha256="b", usuario_carga=user,
                                  fecha=date(2026, 9, 24), numero_corte=2, estado="en_revision")
        Documento.objects.create(corte=c1, factura="603", tipo_comprobante="T")
        Documento.objects.create(corte=c1, factura="56570", tipo_comprobante="F")
        Documento.objects.create(corte=c2, factura="603", tipo_comprobante="T")
        Documento.objects.create(corte=c2, factura="56570", tipo_comprobante="S")  # mismo número, otro tipo

        self.client.force_login(user)
        r = self.client.get(reverse("detalle_corte", args=[c2.pk]))

        self.assertContains(r, 'class="ya-subido"', count=1)
        self.assertContains(r, "ya en Corte 1 · 23 Sep")
