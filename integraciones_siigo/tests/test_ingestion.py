import hashlib
import json
import uuid

from django.test import TestCase, override_settings
from django.urls import reverse

from integraciones_siigo.models import IngestionSiigo


TOKEN = "test-token"
TOKEN_HASH = hashlib.sha256(TOKEN.encode()).hexdigest()
SECOND_TOKEN = "second-test-token"
SECOND_TOKEN_HASH = hashlib.sha256(SECOND_TOKEN.encode()).hexdigest()


@override_settings(SIIGO_INGEST_TOKEN_SHA256=TOKEN_HASH)
class IngestionTests(TestCase):
    def setUp(self):
        self.extraction_id = str(uuid.uuid4())
        self.payload = {
            "schema_version": "1.0",
            "extraction_id": self.extraction_id,
            "source": "siigo",
            "window": {
                "start_date": "2026-07-09",
                "end_date": "2026-07-09",
                "timezone": "America/Bogota",
            },
            "generated_at": "2026-07-09T12:00:00Z",
            "raw_file": {
                "name": "raw.xlsx",
                "sha256": "a" * 64,
                "size_bytes": 100,
            },
            "parser": {"version": "0.1.0", "config_sha256": "b" * 64},
            "row_count": 1,
            "rows": [{"codigo_bodega": "0400"}],
        }
        rows_body = json.dumps(
            self.payload["rows"], ensure_ascii=False, separators=(",", ":")
        ).encode()
        self.payload["rows_sha256"] = hashlib.sha256(rows_body).hexdigest()

    def _post(self, payload=None, token=TOKEN, extraction_id=None):
        body = json.dumps(payload or self.payload, separators=(",", ":")).encode()
        return self.client.post(
            reverse("siigo-ingestion"),
            data=body,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
            HTTP_IDEMPOTENCY_KEY=extraction_id or self.extraction_id,
            HTTP_X_CONTENT_SHA256=hashlib.sha256(body).hexdigest(),
        )

    def test_accepts_and_persists_payload(self):
        response = self._post()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")
        ingestion = IngestionSiigo.objects.get()
        self.assertEqual(ingestion.row_count, 1)
        self.assertEqual(ingestion.payload["rows"][0]["codigo_bodega"], "0400")

    def test_identical_retry_is_duplicate(self):
        self.assertEqual(self._post().status_code, 202)
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "duplicate")
        self.assertEqual(IngestionSiigo.objects.count(), 1)

    def test_rejects_wrong_token(self):
        response = self._post(token="wrong")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(IngestionSiigo.objects.count(), 0)

    @override_settings(
        SIIGO_INGEST_TOKEN_SHA256=f"{TOKEN_HASH}, {SECOND_TOKEN_HASH.upper()}"
    )
    def test_accepts_any_configured_token(self):
        response = self._post(token=SECOND_TOKEN)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")

    @override_settings(
        SIIGO_INGEST_TOKEN_SHA256=f"{TOKEN_HASH},not-a-valid-hash"
    )
    def test_rejects_malformed_token_configuration(self):
        response = self._post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "receiver_not_configured")

    def test_rejects_body_hash_mismatch(self):
        body = json.dumps(self.payload).encode()
        response = self.client.post(
            reverse("siigo-ingestion"),
            data=body,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
            HTTP_IDEMPOTENCY_KEY=self.extraction_id,
            HTTP_X_CONTENT_SHA256="0" * 64,
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_incorrect_row_count(self):
        self.payload["row_count"] = 2
        response = self._post()
        self.assertEqual(response.status_code, 400)

    def test_rejects_idempotency_conflict(self):
        self.assertEqual(self._post().status_code, 202)
        self.payload["raw_file"]["sha256"] = "d" * 64
        response = self._post()
        self.assertEqual(response.status_code, 409)

    def _schema_1_1(self, **cut):
        self.payload["schema_version"] = "1.1"
        self.payload["cut"] = {
            "nombre": "corte_1",
            "desde": "2026-09-24T16:00:00-05:00",
            "hasta": "2026-09-25T11:00:05-05:00",
            "criterio": "fecha_actualizacion+hora_actualizacion en (desde, hasta]",
            "filas_sin_fecha_actualizacion": 0,
            **cut,
        }

    def test_accepts_schema_1_1_with_cut(self):
        self._schema_1_1()
        self.assertEqual(self._post().status_code, 202)
        self.assertEqual(IngestionSiigo.objects.get().payload["cut"]["nombre"], "corte_1")

    def test_rejects_unknown_schema_version(self):
        self.payload["schema_version"] = "2.0"
        self.assertEqual(self._post().status_code, 400)

    def test_rejects_invalid_cut(self):
        for cut in (
            {"nombre": "corte_3"},
            {"desde": "2026-09-24T16:00:00"},  # sin zona horaria
            {"hasta": "2026-09-24T15:00:00-05:00"},  # hasta antes de desde
        ):
            with self.subTest(cut=cut):
                self.setUp()
                self._schema_1_1(**cut)
                self.assertEqual(self._post().status_code, 400)
        self.assertEqual(IngestionSiigo.objects.count(), 0)
