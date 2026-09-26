from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AccesoPlataformaTest(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="operario",
            password="clave-segura-pruebas",
        )

    def test_login_publico_usa_la_plantilla_de_la_plataforma(self):
        respuesta = self.client.get(reverse("login"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "admin/login.html")
        self.assertContains(respuesta, 'action="/login/"')

    def test_vista_protegida_redirige_al_login_publico(self):
        respuesta = self.client.get(reverse("lista_cortes"))

        self.assertRedirects(
            respuesta,
            f'{reverse("login")}?next={reverse("lista_cortes")}',
            fetch_redirect_response=False,
        )

    def test_login_publico_autentica_y_respeta_next(self):
        respuesta = self.client.post(
            reverse("login"),
            {
                "username": self.usuario.username,
                "password": "clave-segura-pruebas",
                "next": reverse("lista_cortes"),
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("lista_cortes"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session.get("_auth_user_id"),
            str(self.usuario.pk),
        )

    def test_admin_conserva_su_ruta_independiente(self):
        respuesta = self.client.get(reverse("admin:login"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(reverse("admin:login"), "/admin/login/")
