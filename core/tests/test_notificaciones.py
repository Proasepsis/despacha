from datetime import date

from django.test import TestCase, override_settings
from django.core import mail
from django.contrib.auth.models import User

from cortes.models import Corte
from core.models import NotificacionDestinatarios
from core.servicios.notificaciones import (
    notificar_corte_generado,
    notificar_corte_regenerado,
    notificar_sin_maestra_detectado,
    _prefijo_asunto,
)


class NotificacionesTest(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username="op1", password="test")
        self.corte = Corte.objects.create(
            archivo="test.xlsx",
            hash_sha256="abc_notif",
            usuario_carga=self.usuario,
            fecha=date(2026, 5, 5),
            numero_corte=1,
            estado="generado",
            version_actual=1,
        )

        for evento in ["corte_generado", "corte_regenerado", "sin_maestro_detectado"]:
            NotificacionDestinatarios.objects.update_or_create(
                evento=evento,
                defaults={"correos": "despacho@proasepsis.com", "activo": True},
            )

    def test_notificar_corte_generado(self):
        result = notificar_corte_generado(self.corte)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("generado", mail.outbox[0].subject)

    def test_notificar_corte_regenerado(self):
        self.corte.version_actual = 2
        self.corte.save()
        result = notificar_corte_regenerado(self.corte)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ATENCI", mail.outbox[0].subject)
        self.assertIn("v2", mail.outbox[0].subject)

    def test_notificar_sin_maestra(self):
        result = notificar_sin_maestra_detectado(self.corte, ["1500005000005"])
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("1500005000005", mail.outbox[0].body)

    def test_no_destinatarios_no_envia(self):
        NotificacionDestinatarios.objects.filter(evento="corte_generado").delete()
        result = notificar_corte_generado(self.corte)
        self.assertFalse(result)

    def test_destinatario_inactivo_no_envia(self):
        NotificacionDestinatarios.objects.filter(evento="corte_generado").update(activo=False)
        result = notificar_corte_generado(self.corte)
        self.assertFalse(result)

    @override_settings()
    def test_prefijo_staging(self):
        import os
        old = os.environ.get("ENVIRONMENT", "")
        os.environ["ENVIRONMENT"] = "staging"
        try:
            self.assertEqual(_prefijo_asunto(), "[STAGING] ")
        finally:
            os.environ["ENVIRONMENT"] = old
