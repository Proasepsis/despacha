import hashlib
from io import StringIO
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from api_vigia.models import CredencialVigia
from core.models import ParametroSalida
from cortes.models import Corte, CorteVersion, Documento, Linea


TOKEN = "vigia_1234567890abcdef_secret-test"


class ApiVigiaTests(TestCase):
    def setUp(self):
        self.credential = CredencialVigia.objects.create(
            nombre="api-vigia-test",
            identificador="1234567890abcdef",
            token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
        )
        self.user = User.objects.create_user("api-test")
        self.generated = self._corte("generado", date(2026, 7, 8), "generated")
        self.review = self._corte("en_revision", date(2026, 7, 9), "review")
        for key, value in (
            ("punto", "BODEGA PRINCIPAL"),
            ("identificacion", "900123"),
            ("nombre", "PROASEPSIS"),
        ):
            ParametroSalida.objects.update_or_create(
                clave=key, defaults={"valor": value}
            )

    def _corte(self, estado, fecha, suffix):
        corte = Corte.objects.create(
            archivo=f"{suffix}.xlsx",
            hash_sha256=hashlib.sha256(suffix.encode()).hexdigest(),
            usuario_carga=self.user,
            fecha=fecha,
            numero_corte=1 if estado == "generado" else 2,
            estado=estado,
            version_actual=1 if estado == "generado" else 0,
        )
        document = Documento.objects.create(
            corte=corte,
            factura=f"F-{suffix}",
            nit="900123",
            tipo_comprobante="F",
            clasificador1="EMBALAR",
            observaciones="PRIORIDAD",
        )
        Linea.objects.create(
            documento=document,
            referencia="REF",
            lote="LOTE.",
            cantidad_origen=Decimal("2"),
            cantidad_unidades=4,
            referencia_snapshot="1500005000005",
            descripcion_snapshot="PRODUCTO",
            unidad_empaque_snapshot=2,
        )
        if estado == "generado":
            CorteVersion.objects.create(
                corte=corte,
                numero=1,
                archivo_hash="a" * 64,
                usuario=self.user,
            )
        return corte

    def _get(self, url, token=TOKEN, **headers):
        return self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {token}",
            **headers,
        )

    def test_requires_token(self):
        response = self.client.get(reverse("api_vigia:listar_cortes"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Bearer")

    def test_rejects_wrong_token(self):
        response = self._get(reverse("api_vigia:listar_cortes"), token="wrong")
        self.assertEqual(response.status_code, 401)

    def test_restricts_configured_ip(self):
        self.credential.ips_permitidas = ["10.20.30.0/24"]
        self.credential.save(update_fields=["ips_permitidas"])
        denied = self._get(
            reverse("api_vigia:listar_cortes"), HTTP_X_REAL_IP="192.168.1.20"
        )
        allowed = self._get(
            reverse("api_vigia:listar_cortes"), HTTP_X_REAL_IP="10.20.30.40"
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)

    def test_ignores_forwarded_ip_from_untrusted_source(self):
        self.credential.ips_permitidas = ["10.20.30.0/24"]
        self.credential.save(update_fields=["ips_permitidas"])
        response = self.client.get(
            reverse("api_vigia:listar_cortes"),
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
            HTTP_X_REAL_IP="10.20.30.40",
            REMOTE_ADDR="203.0.113.5",
        )
        self.assertEqual(response.status_code, 403)

    def test_empty_ip_allowlist_means_any_ip(self):
        self.assertFalse(self.credential.ips_permitidas)
        response = self._get(
            reverse("api_vigia:listar_cortes"), HTTP_X_REAL_IP="198.51.100.7"
        )
        self.assertEqual(response.status_code, 200)

    def test_lists_only_generated_cuts(self):
        response = self._get(
            reverse("api_vigia:listar_cortes") + "?fecha_desde=2026-01-01"
        )
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ids, [self.generated.id])

    def test_validates_query_and_paginates(self):
        invalid = self._get(reverse("api_vigia:listar_cortes") + "?page_size=101")
        self.assertEqual(invalid.status_code, 400)

        second = self._corte("generado", date(2026, 7, 10), "second")
        response = self._get(
            reverse("api_vigia:listar_cortes")
            + "?fecha_desde=2026-01-01&page_size=1"
        )
        self.assertTrue(response.json()["has_more"])
        cursor = response.json()["next_cursor"]
        next_page = self._get(
            reverse("api_vigia:listar_cortes")
            + f"?fecha_desde=2026-01-01&page_size=1&cursor={cursor}"
        )
        self.assertEqual(next_page.json()["results"][0]["id"], second.id)

    def test_incremental_feed_reflects_updated_cuts(self):
        Corte.objects.filter(pk=self.generated.pk).update(
            actualizado_en=timezone.now()
        )
        marker = timezone.now() - timedelta(seconds=1)
        query = urlencode({"actualizado_desde": marker.isoformat()})
        response = self._get(reverse("api_vigia:listar_cortes") + f"?{query}")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ids, [self.generated.id])

    def test_detail_paginates_documents(self):
        second = Documento.objects.create(
            corte=self.generated,
            factura="F-segundo",
            nit="900123",
            tipo_comprobante="F",
        )
        url = reverse("api_vigia:detalle_corte", args=[self.generated.id])
        first_page = self._get(url + "?page_size=1")
        data = first_page.json()["data"]
        self.assertEqual(len(data["documentos"]), 1)
        self.assertTrue(data["documentos_has_more"])
        next_page = self._get(
            url + f"?page_size=1&documento_cursor={data['documentos_next_cursor']}"
        )
        next_data = next_page.json()["data"]
        self.assertEqual(len(next_data["documentos"]), 1)
        self.assertFalse(next_data["documentos_has_more"])
        returned_ids = {
            data["documentos"][0]["id"],
            next_data["documentos"][0]["id"],
        }
        self.assertIn(second.id, returned_ids)

    def test_detail_omits_customer_master_data(self):
        url = reverse("api_vigia:detalle_corte", args=[self.generated.id])
        response = self._get(url)
        documento = response.json()["data"]["documentos"][0]
        self.assertNotIn("cliente", documento)
        self.assertIn("nit", documento)

    def test_documentos_dia_returns_detailed_documents(self):
        response = self._get(
            reverse("api_vigia:documentos_dia") + "?fecha=2026-07-08"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["fecha"], "2026-07-08")
        facturas = [documento["factura"] for documento in payload["documentos"]]
        self.assertEqual(facturas, ["F-generated"])
        documento = payload["documentos"][0]
        self.assertEqual(documento["tipo_comprobante"], "F")
        self.assertEqual(documento["corte"]["id"], self.generated.id)
        self.assertEqual(documento["lineas"][0]["articulo"], "1500005000005")

    def test_documentos_dia_filters_type_and_paginates(self):
        Documento.objects.create(
            corte=self.generated,
            factura="T-1",
            nit="900123",
            tipo_comprobante="T",
        )
        solo_t = self._get(
            reverse("api_vigia:documentos_dia") + "?fecha=2026-07-08&tipo=T"
        )
        self.assertEqual(
            [documento["factura"] for documento in solo_t.json()["documentos"]],
            ["T-1"],
        )
        solo_f = self._get(
            reverse("api_vigia:documentos_dia") + "?fecha=2026-07-08&tipo=F"
        )
        self.assertEqual(
            [documento["factura"] for documento in solo_f.json()["documentos"]],
            ["F-generated"],
        )

        first_page = self._get(
            reverse("api_vigia:documentos_dia") + "?fecha=2026-07-08&page_size=1"
        )
        payload = first_page.json()
        self.assertTrue(payload["has_more"])
        next_page = self._get(
            reverse("api_vigia:documentos_dia")
            + f"?fecha=2026-07-08&page_size=1&documento_cursor={payload['next_cursor']}"
        )
        self.assertFalse(next_page.json()["has_more"])

    def test_documentos_dia_validates_date_and_hides_review(self):
        invalid = self._get(
            reverse("api_vigia:documentos_dia") + "?fecha=no-es-fecha"
        )
        self.assertEqual(invalid.status_code, 400)
        invalid_tipo = self._get(
            reverse("api_vigia:documentos_dia") + "?fecha=2026-07-08&tipo=X"
        )
        self.assertEqual(invalid_tipo.status_code, 400)

        review_day = self._get(
            reverse("api_vigia:documentos_dia") + "?fecha=2026-07-09"
        )
        self.assertEqual(review_day.status_code, 200)
        self.assertEqual(review_day.json()["count"], 0)

    def test_detail_matches_ready_output_and_supports_etag(self):
        url = reverse("api_vigia:detalle_corte", args=[self.generated.id])
        response = self._get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["version"], 1)
        line = data["documentos"][0]["lineas"][0]
        self.assertEqual(line["articulo"], "1500005000005")
        self.assertEqual(line["lote"], "LOTE")
        self.assertEqual(line["cantidad"], "4")

        cached = self._get(url, HTTP_IF_NONE_MATCH=response["ETag"])
        self.assertEqual(cached.status_code, 304)

        other_page = self._get(url + "?page_size=1")
        wrong_etag = self._get(
            url + "?page_size=1", HTTP_IF_NONE_MATCH=response["ETag"]
        )
        self.assertNotEqual(response["ETag"], other_page["ETag"])
        self.assertEqual(wrong_etag.status_code, 200)

    def test_non_generated_detail_is_hidden(self):
        response = self._get(
            reverse("api_vigia:detalle_corte", args=[self.review.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_records_last_use(self):
        self._get(reverse("api_vigia:listar_cortes"), HTTP_X_REAL_IP="10.1.2.3")
        self.credential.refresh_from_db()
        self.assertEqual(self.credential.ultima_ip, "10.1.2.3")
        self.assertIsNotNone(self.credential.ultimo_uso_en)

    def test_management_command_rotates_token(self):
        output = StringIO()
        call_command(
            "crear_credencial_vigia", "nuevo-cliente", "--ip", "10.0.0.0/8",
            stdout=output,
        )
        token = output.getvalue().strip()
        created = CredencialVigia.objects.get(nombre="nuevo-cliente")
        self.assertTrue(token.startswith(f"vigia_{created.identificador}_"))
        self.assertEqual(
            created.token_sha256,
            hashlib.sha256(token.encode()).hexdigest(),
        )
        self.assertEqual(created.ips_permitidas, ["10.0.0.0/8"])

        with self.assertRaises(CommandError):
            call_command("crear_credencial_vigia", "api-vigia-test")

        with self.assertRaises(CommandError):
            call_command("crear_credencial_vigia", "mal-ip", "--ip", "999.1.1.1")

        with self.assertRaises(CommandError):
            call_command("crear_credencial_vigia", "   ")

        with self.assertRaises(CommandError):
            call_command("crear_credencial_vigia", "sin-ip-ni-bandera")

        abierta = StringIO()
        call_command(
            "crear_credencial_vigia",
            "abierta-deliberadamente",
            "--permitir-cualquier-ip",
            stdout=abierta,
        )
        creada_abierta = CredencialVigia.objects.get(
            nombre="abierta-deliberadamente"
        )
        self.assertEqual(creada_abierta.ips_permitidas, [])
