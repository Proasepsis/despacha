import hashlib
import json
import uuid
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from integraciones_siigo import solicitudes
from integraciones_siigo.models import FilaSiigo, IngestionSiigo, SolicitudExtraccion

TOKEN = "test-token"
con_token = override_settings(SIIGO_INGEST_TOKEN_SHA256=hashlib.sha256(TOKEN.encode()).hexdigest())
AUTH = {"HTTP_AUTHORIZATION": f"Bearer {TOKEN}"}
HOY = timezone.localdate()


def fila(num, seq, dia=date(2026, 9, 30), tipo="F"):
    return {
        "tipo_comprobante": tipo, "codigo_comprobante": "1", "numero_documento": num,
        "secuencia": seq, "anio_documento": dia.year, "mes_documento": dia.month,
        "dia_documento": dia.day,
    }


def payload(rows, schema="1.2", cut=None, solicitud_id=None):
    p = {
        "schema_version": schema, "extraction_id": str(uuid.uuid4()), "source": "siigo",
        "window": {"start_date": "2026-09-30", "end_date": "2026-09-30"},
        "generated_at": "2026-10-01T12:00:00Z",
        "raw_file": {"name": "r.xlsx", "sha256": "a" * 64, "size_bytes": 1},
        "row_count": len(rows), "rows": rows,
        "rows_sha256": hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    if cut:
        p["cut"] = cut
    if solicitud_id:
        p["solicitud_id"] = str(solicitud_id)
    return p


def cut_solicitud(desde="2026-09-30", hasta="2026-09-30"):
    return {"nombre": "solicitud", "criterio": "dia_completo_por_fecha_documento", "desde": desde, "hasta": hasta}


class Base:
    def post_ingesta(self, p):
        body = json.dumps(p, separators=(",", ":")).encode()
        return self.client.post(
            reverse("siigo-ingestion"), data=body, content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=p["extraction_id"],
            HTTP_X_CONTENT_SHA256=hashlib.sha256(body).hexdigest(), **AUTH,
        )

    def tomar(self):
        return self.client.post(reverse("siigo-solicitud-tomar"), **AUTH)

    def estado(self, sid, **body):
        return self.client.post(
            reverse("siigo-solicitud-estado", args=[sid]), data=json.dumps(body),
            content_type="application/json", **AUTH,
        )

    def nueva(self, ini=date(2026, 9, 30), fin=date(2026, 9, 30)):
        return SolicitudExtraccion.objects.create(fecha_inicio=ini, fecha_fin=fin)


@con_token
class TomarTests(Base, TestCase):
    def test_sin_pendientes_204(self):
        r = self.tomar()
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r.content, b"")

    def test_requiere_token(self):
        self.assertEqual(self.client.post(reverse("siigo-solicitud-tomar")).status_code, 401)

    def test_toma_la_mas_antigua_y_cuenta_intento(self):
        vieja, _ = self.nueva(), self.nueva(date(2026, 9, 1), date(2026, 9, 2))
        r = self.tomar()
        self.assertEqual(r.json(), {
            "solicitud_id": str(vieja.solicitud_id), "fecha_inicio": "2026-09-30", "fecha_fin": "2026-09-30",
        })
        vieja.refresh_from_db()
        self.assertEqual((vieja.estado, vieja.intentos), ("tomada", 1))
        self.assertIsNotNone(vieja.tomada_en)

    def test_no_entrega_la_misma_dos_veces(self):
        self.nueva()
        self.assertEqual(self.tomar().status_code, 200)
        self.assertEqual(self.tomar().status_code, 204)

    def test_segunda_llamada_pierde_la_carrera(self):
        # El UPDATE condicional afecta 0 filas si otra llamada ya la tomó: se pasa a la siguiente
        a, b = self.nueva(), self.nueva()
        real = SolicitudExtraccion.objects.filter
        llamado = []

        def filter_con_carrera(*args, **kw):
            if kw.get("pk") == a.pk and not llamado:
                llamado.append(1)
                SolicitudExtraccion.objects.filter(pk=a.pk).update(estado="tomada")  # otro agente la ganó
            return real(*args, **kw)

        from unittest import mock
        with mock.patch.object(SolicitudExtraccion.objects, "filter", side_effect=filter_con_carrera):
            tomada = solicitudes.tomar_siguiente()
        self.assertEqual(tomada.pk, b.pk)

    def test_tomada_vencida_vuelve_a_pendiente(self):
        s = self.nueva()
        self.tomar()
        SolicitudExtraccion.objects.filter(pk=s.pk).update(tomada_en=timezone.now() - timedelta(minutes=21))
        self.assertEqual(self.tomar().json()["solicitud_id"], str(s.solicitud_id))
        s.refresh_from_db()
        self.assertEqual(s.intentos, 2)

    def test_tomada_reciente_no_vence(self):
        self.nueva()
        self.tomar()
        SolicitudExtraccion.objects.update(tomada_en=timezone.now() - timedelta(minutes=19))
        self.assertEqual(self.tomar().status_code, 204)

    def test_tercer_vencimiento_falla(self):
        s = self.nueva()
        SolicitudExtraccion.objects.filter(pk=s.pk).update(
            estado="tomada", intentos=3, tomada_en=timezone.now() - timedelta(minutes=30)
        )
        self.assertEqual(self.tomar().status_code, 204)
        s.refresh_from_db()
        self.assertEqual((s.estado, s.error), ("fallida", "sin respuesta del agente"))


@con_token
class ConcurrenciaTests(Base, TransactionTestCase):
    def test_hilos_no_toman_la_misma(self):
        import threading
        if connection.vendor == "sqlite":
            self.skipTest("SQLite en memoria no soporta conexiones concurrentes; cubierto por test_segunda_llamada_pierde_la_carrera")
        for _ in range(3):
            self.nueva()
        ids, lock = [], threading.Lock()

        def tomar():
            s = solicitudes.tomar_siguiente()
            with lock:
                ids.append(s and s.pk)
            connection.close()

        hilos = [threading.Thread(target=tomar) for _ in range(3)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        self.assertEqual(len(set(ids)), 3)


@con_token
class IngestaSolicitudTests(Base, TestCase):
    def enviar(self, rows, s, **kw):
        return self.post_ingesta(payload(rows, cut=cut_solicitud(), solicitud_id=s.solicitud_id, **kw))

    def test_acepta_schema_11_y_12(self):
        cut11 = {"nombre": "corte_1", "desde": "2026-09-30T00:00:00-05:00", "hasta": "2026-09-30T11:00:00-05:00"}
        self.assertEqual(self.post_ingesta(payload([{"a": 1}], schema="1.1", cut=cut11)).status_code, 202)
        self.assertEqual(self.post_ingesta(payload([fila("1", "1")], schema="1.2", cut=cut11)).status_code, 202)

    def test_12_exige_campos_nuevos(self):
        r = self.post_ingesta(payload([{"tipo_comprobante": "F"}], schema="1.2"))
        self.assertEqual(r.status_code, 400)

    def test_schema_desconocido(self):
        self.assertEqual(self.post_ingesta(payload([], schema="1.3")).status_code, 400)

    def test_solicitud_requiere_12(self):
        s = self.nueva(); self.tomar()
        r = self.post_ingesta(payload([], schema="1.1", cut=cut_solicitud(), solicitud_id=s.solicitud_id))
        self.assertEqual(r.status_code, 400)

    def test_solicitud_inexistente_404(self):
        r = self.post_ingesta(payload([fila("1", "1")], cut=cut_solicitud(), solicitud_id=uuid.uuid4()))
        self.assertEqual(r.status_code, 404)

    def test_solicitud_no_tomada_409(self):
        s = self.nueva()
        self.assertEqual(self.enviar([fila("1", "1")], s).status_code, 409)
        self.assertEqual(IngestionSiigo.objects.count(), 0)

    def test_cut_distinto_a_la_solicitud_400(self):
        s = self.nueva(); self.tomar()
        r = self.post_ingesta(payload([fila("1", "1")], cut=cut_solicitud("2026-09-29", "2026-09-30"), solicitud_id=s.solicitud_id))
        self.assertEqual(r.status_code, 400)

    def test_guarda_filas_y_vincula(self):
        s = self.nueva(); self.tomar()
        r = self.enviar([fila("56651", "1"), fila("56651", "2")], s)
        self.assertEqual(r.status_code, 202)
        self.assertEqual(FilaSiigo.objects.count(), 2)
        self.assertEqual(IngestionSiigo.objects.get().solicitud, s)

    def test_reemplaza_no_suma(self):
        s1 = self.nueva(); self.tomar()
        self.enviar([fila("56651", str(i)) for i in range(1, 4)], s1)
        self.estado(s1.solicitud_id, estado="completada", extraction_id=None, row_count=None, error=None)
        s2 = self.nueva(); self.tomar()
        self.enviar([fila("56651", "1"), fila("56651", "9")], s2)
        self.assertEqual(
            sorted(FilaSiigo.objects.values_list("secuencia", flat=True)), ["1", "9"]
        )

    def test_marca_ausentes_sin_borrar(self):
        s1 = self.nueva(); self.tomar()
        self.enviar([fila("1", "1"), fila("2", "1")], s1)
        self.estado(s1.solicitud_id, estado="completada")
        s2 = self.nueva(); self.tomar()
        self.enviar([fila("1", "1")], s2)
        self.assertFalse(FilaSiigo.objects.get(numero_documento="1").no_presente_en_siigo)
        self.assertTrue(FilaSiigo.objects.get(numero_documento="2").no_presente_en_siigo)

    def test_ausentes_solo_dentro_del_rango(self):
        FilaSiigo.objects.create(
            tipo_comprobante="F", codigo_comprobante="1", numero_documento="OTRO", secuencia="1",
            fecha_documento=date(2026, 8, 1), fila={}, ingestion=IngestionSiigo.objects.create(
                extraction_id=uuid.uuid4(), schema_version="1.2", source="siigo", window_start=HOY,
                window_end=HOY, generated_at=timezone.now(), raw_sha256="a", raw_size_bytes=1,
                content_sha256="a", rows_sha256="a", row_count=0, payload={},
            ),
        )
        s = self.nueva(); self.tomar()
        self.enviar([fila("1", "1")], s)
        self.assertFalse(FilaSiigo.objects.get(numero_documento="OTRO").no_presente_en_siigo)

    def test_mismo_numero_distinto_tipo_son_documentos_distintos(self):
        s = self.nueva(); self.tomar()
        self.enviar([fila("603", "1", tipo="F"), fila("603", "1", tipo="T")], s)
        self.assertEqual(FilaSiigo.objects.count(), 2)

    def test_reintento_idempotente_tras_completar(self):
        s = self.nueva(); self.tomar()
        p = payload([fila("1", "1")], cut=cut_solicitud(), solicitud_id=s.solicitud_id)
        self.assertEqual(self.post_ingesta(p).status_code, 202)
        self.estado(s.solicitud_id, estado="completada")
        r = self.post_ingesta(p)
        self.assertEqual((r.status_code, r.json()["status"]), (200, "duplicate"))


@con_token
class EstadoTests(Base, TestCase):
    def test_404(self):
        self.assertEqual(self.estado(uuid.uuid4(), estado="fallida", error="x").status_code, 404)

    def test_409_si_no_esta_tomada(self):
        s = self.nueva()
        self.assertEqual(self.estado(s.solicitud_id, estado="fallida", error="x").status_code, 409)

    def test_409_si_ya_tiene_estado_final(self):
        s = self.nueva(); self.tomar()
        self.estado(s.solicitud_id, estado="fallida", error="x")
        self.assertEqual(self.estado(s.solicitud_id, estado="fallida", error="y").status_code, 409)

    def test_completada_sin_ingesta_409(self):
        s = self.nueva(); self.tomar()
        r = self.estado(s.solicitud_id, estado="completada", extraction_id=None, row_count=0, error=None)
        self.assertEqual(r.status_code, 409)
        s.refresh_from_db()
        self.assertEqual(s.estado, "tomada")

    def test_completada_con_ingesta(self):
        s = self.nueva(); self.tomar()
        p = payload([fila("1", "1")], cut=cut_solicitud(), solicitud_id=s.solicitud_id)
        self.post_ingesta(p)
        r = self.estado(s.solicitud_id, estado="completada", extraction_id=p["extraction_id"], row_count=1, error=None)
        self.assertEqual(r.json(), {"solicitud_id": str(s.solicitud_id), "estado": "completada"})
        s.refresh_from_db()
        self.assertEqual((s.row_count, s.completada_en is not None), (1, True))

    def test_completada_con_extraction_ajena_409(self):
        s = self.nueva(); self.tomar()
        self.post_ingesta(payload([fila("1", "1")], cut=cut_solicitud(), solicitud_id=s.solicitud_id))
        r = self.estado(s.solicitud_id, estado="completada", extraction_id=str(uuid.uuid4()))
        self.assertEqual(r.status_code, 409)

    def test_fallida_guarda_error(self):
        s = self.nueva(); self.tomar()
        self.assertEqual(self.estado(s.solicitud_id, estado="fallida", error="GETMOV falló").status_code, 200)
        s.refresh_from_db()
        self.assertEqual((s.estado, s.error), ("fallida", "GETMOV falló"))

    def test_estado_invalido_400(self):
        s = self.nueva(); self.tomar()
        self.assertEqual(self.estado(s.solicitud_id, estado="pendiente").status_code, 400)


class CrearSolicitudTests(TestCase):
    def test_validaciones(self):
        u = None
        malos = [
            (date(2026, 9, 30), date(2026, 9, 29)),
            (date(2025, 12, 31), date(2026, 1, 1)),
            (date(2026, 1, 1), date(2026, 2, 2)),
            (HOY, HOY + timedelta(days=1)),
        ]
        for ini, fin in malos:
            with self.assertRaises(ValueError, msg=(ini, fin)):
                solicitudes.crear_solicitud(ini, fin, u)
        self.assertEqual(SolicitudExtraccion.objects.count(), 0)
        solicitudes.crear_solicitud(date(2026, 1, 1), date(2026, 1, 31), u)
        self.assertEqual(SolicitudExtraccion.objects.get().estado, "pendiente")


class PantallaTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adm", password="x")
        self.admin.groups.add(Group.objects.get_or_create(name="admin")[0])

    def test_solo_admin(self):
        otro = User.objects.create_user("otro", password="x")
        self.client.force_login(otro)
        self.assertEqual(self.client.get(reverse("siigo-solicitudes")).status_code, 403)

    def test_crear_y_listar(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("siigo-solicitudes"), {"fecha_inicio": "2026-09-30", "fecha_fin": "2026-09-30"})
        self.assertEqual(r.status_code, 302)
        s = SolicitudExtraccion.objects.get()
        self.assertEqual(s.creada_por, self.admin)
        self.assertContains(self.client.get(reverse("siigo-solicitudes")), "adm")

    def test_rango_invalido_no_crea(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("siigo-solicitudes"), {"fecha_inicio": "2026-09-30", "fecha_fin": "2026-09-01"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(SolicitudExtraccion.objects.count(), 0)
