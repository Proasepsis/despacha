from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User, Group

from cortes.models import Auditoria
from core.servicios.auditoria import registrar


class AuditoriaTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_test", password="test")
        grupo, _ = Group.objects.get_or_create(name="admin")
        self.admin.groups.add(grupo)

    def test_registrar_crea_entrada(self):
        auditoria = registrar(
            usuario=self.admin,
            objeto_tipo="Corte",
            objeto_id=1,
            tipo_evento="creacion",
            campo="estado",
            valor_anterior="cargado",
            valor_nuevo="generado",
        )
        self.assertEqual(auditoria.objeto_tipo, "Corte")
        self.assertEqual(auditoria.campo, "estado")
        self.assertEqual(Auditoria.objects.count(), 1)

    def test_registrar_valores_none(self):
        auditoria = registrar(
            usuario=self.admin,
            objeto_tipo="Test",
            objeto_id="X",
            tipo_evento="edicion",
            valor_anterior=None,
            valor_nuevo=None,
        )
        self.assertEqual(auditoria.valor_anterior, "")
        self.assertEqual(auditoria.valor_nuevo, "")

    def test_registrar_metadata(self):
        auditoria = registrar(
            usuario=self.admin,
            objeto_tipo="User",
            objeto_id="anon",
            tipo_evento="login_fallido",
            metadata={"ip": "192.168.1.1"},
        )
        self.assertEqual(auditoria.metadata, {"ip": "192.168.1.1"})

    def test_vista_auditoria_requiere_admin(self):
        user = User.objects.create_user(username="op", password="test")
        grupo, _ = Group.objects.get_or_create(name="operario")
        user.groups.add(grupo)

        self.client.login(username="op", password="test")
        response = self.client.get(reverse("admin_auditoria"))
        self.assertEqual(response.status_code, 403)

    def test_vista_auditoria_admin_accede(self):
        self.client.login(username="admin_test", password="test")
        response = self.client.get(reverse("admin_auditoria"))
        self.assertEqual(response.status_code, 200)

    def test_vista_export_csv(self):
        self.client.login(username="admin_test", password="test")
        registrar(
            usuario=self.admin,
            objeto_tipo="Documento",
            objeto_id=5,
            tipo_evento="edicion",
            campo="clasificador1",
            valor_anterior="EMBALAR",
            valor_nuevo="NO EMBALAR",
        )
        response = self.client.get(reverse("admin_auditoria") + "?export=csv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode()
        self.assertIn("clasificador1", content)
