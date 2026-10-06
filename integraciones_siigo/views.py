import hashlib
import hmac
import json
import re
import uuid
from datetime import date

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import solicitudes
from .models import IngestionSiigo, SolicitudExtraccion


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SCHEMAS_SOPORTADOS = {"1.0", "1.1", "1.2"}
CAMPOS_1_2 = ("anio_documento", "mes_documento", "dia_documento", "secuencia")
NOMBRES_CUT = {"corte_1", "corte_2", "extra", "recuperacion"}
NOMBRE_SOLICITUD = "solicitud"


@csrf_exempt
@require_POST
def ingest_siigo(request):
    auth_error = _authenticate(request)
    if auth_error is not None:
        return auth_error

    body_hash = hashlib.sha256(request.body).hexdigest()
    supplied_body_hash = request.headers.get("X-Content-SHA256", "").lower()
    if not hmac.compare_digest(body_hash, supplied_body_hash):
        return _error("content_hash_mismatch", 400)

    try:
        payload = json.loads(request.body)
        validated = _validate_payload(payload, request.headers.get("Idempotency-Key"))
    except (json.JSONDecodeError, TypeError, ValueError, KeyError) as error:
        return _error("invalid_payload", 400, str(error))

    with transaction.atomic():
        extraction_id = validated.pop("extraction_id")
        solicitud_id = validated.pop("solicitud_id")
        ingestion = IngestionSiigo.objects.filter(extraction_id=extraction_id).first()
        if ingestion is not None:
            if not hmac.compare_digest(ingestion.content_sha256, body_hash):
                return _error("idempotency_conflict", 409)
            return _acuse(ingestion, "duplicate", 200)

        solicitud = None
        if solicitud_id:
            solicitud = SolicitudExtraccion.objects.select_for_update().filter(solicitud_id=solicitud_id).first()
            if solicitud is None:
                return _error("solicitud_no_existe", 404)
            if solicitud.estado != SolicitudExtraccion.TOMADA:
                return _error("solicitud_no_tomada", 409)
            cut = payload["cut"]
            if (cut["desde"], cut["hasta"]) != (str(solicitud.fecha_inicio), str(solicitud.fecha_fin)):
                return _error("invalid_payload", 400, "cut no coincide con la solicitud")
        ingestion = IngestionSiigo.objects.create(
            extraction_id=extraction_id,
            solicitud=solicitud,
            content_sha256=body_hash,
            payload=payload,
            source_ip=_source_ip(request),
            **validated,
        )
        if solicitud is not None:
            solicitudes.reemplazar_filas(ingestion, solicitud.fecha_inicio, solicitud.fecha_fin)
    return _acuse(ingestion, "accepted", 202)


def _acuse(ingestion, status_text, status):
    return JsonResponse(
        {
            "extraction_id": str(ingestion.extraction_id),
            "raw_sha256": ingestion.raw_sha256,
            "status": status_text,
        },
        status=status,
    )


@csrf_exempt
@require_POST
def tomar_solicitud(request):
    auth_error = _authenticate(request)
    if auth_error is not None:
        return auth_error
    solicitud = solicitudes.tomar_siguiente()
    if solicitud is None:
        return HttpResponse(status=204)
    return JsonResponse(
        {
            "solicitud_id": str(solicitud.solicitud_id),
            "fecha_inicio": str(solicitud.fecha_inicio),
            "fecha_fin": str(solicitud.fecha_fin),
        }
    )


@csrf_exempt
@require_POST
def estado_solicitud(request, solicitud_id):
    auth_error = _authenticate(request)
    if auth_error is not None:
        return auth_error
    try:
        body = json.loads(request.body)
        estado = body["estado"]
        extraction_id = body.get("extraction_id")
        row_count = body.get("row_count")
        error = body.get("error") or ""
        if estado not in (SolicitudExtraccion.COMPLETADA, SolicitudExtraccion.FALLIDA):
            raise ValueError("estado inválido")
        if extraction_id is not None:
            extraction_id = uuid.UUID(str(extraction_id))
        if row_count is not None and (not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0):
            raise ValueError("row_count inválido")
        if not isinstance(error, str):
            raise ValueError("error inválido")
    except (json.JSONDecodeError, TypeError, ValueError, KeyError, AttributeError) as e:
        return _error("invalid_payload", 400, str(e))

    with transaction.atomic():
        solicitud = SolicitudExtraccion.objects.select_for_update().filter(solicitud_id=solicitud_id).first()
        if solicitud is None:
            return _error("solicitud_no_existe", 404)
        if solicitud.estado != SolicitudExtraccion.TOMADA:
            return _error("solicitud_no_tomada", 409)
        if estado == SolicitudExtraccion.COMPLETADA:
            ingestiones = solicitud.ingestiones.all()
            if extraction_id is not None:
                ingestiones = ingestiones.filter(extraction_id=extraction_id)
            ingestion = ingestiones.first()
            if ingestion is None:
                return _error("sin_ingesta", 409)
            extraction_id = ingestion.extraction_id
            if row_count is None:
                row_count = ingestion.row_count
        solicitud.estado = estado
        solicitud.extraction_id = extraction_id
        solicitud.row_count = row_count
        solicitud.error = error[:1000]
        solicitud.completada_en = timezone.now()
        solicitud.save()
    return JsonResponse({"solicitud_id": str(solicitud.solicitud_id), "estado": estado})


def _authenticate(request):
    expected_hashes = [
        value.strip().lower() for value in settings.SIIGO_INGEST_TOKEN_SHA256.split(",")
    ]
    if any(not SHA256_PATTERN.fullmatch(value) for value in expected_hashes):
        return _error("receiver_not_configured", 503)
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return _error("unauthorized", 401)
    token = authorization.removeprefix("Bearer ")
    received_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not any(
        hmac.compare_digest(received_hash, expected_hash) for expected_hash in expected_hashes
    ):
        return _error("unauthorized", 401)
    return None


def _validate_payload(payload, idempotency_key):
    if not isinstance(payload, dict):
        raise ValueError("El cuerpo debe ser un objeto JSON")
    extraction_id = uuid.UUID(str(payload["extraction_id"]))
    if not hmac.compare_digest(str(extraction_id), idempotency_key or ""):
        raise ValueError("Idempotency-Key no coincide con extraction_id")
    if payload["schema_version"] not in SCHEMAS_SOPORTADOS:
        raise ValueError("schema_version no soportada")
    if "cut" in payload:
        _validate_cut(payload["cut"])
    es_solicitud = payload.get("cut", {}).get("nombre") == NOMBRE_SOLICITUD
    solicitud_id = None
    if es_solicitud:
        if payload["schema_version"] != "1.2":
            raise ValueError("Una solicitud requiere schema_version 1.2")
        solicitud_id = uuid.UUID(str(payload["solicitud_id"]))
    elif "solicitud_id" in payload:
        raise ValueError("solicitud_id solo aplica con cut.nombre=solicitud")
    if payload["source"] != "siigo":
        raise ValueError("source no soportado")

    window_start = parse_date(payload["window"]["start_date"])
    window_end = parse_date(payload["window"]["end_date"])
    generated_at = parse_datetime(payload["generated_at"])
    if window_start is None or window_end is None or generated_at is None:
        raise ValueError("Fechas inválidas")
    if window_end < window_start:
        raise ValueError("Ventana inválida")

    raw_sha256 = str(payload["raw_file"]["sha256"]).lower()
    rows_sha256 = str(payload["rows_sha256"]).lower()
    if not SHA256_PATTERN.fullmatch(raw_sha256):
        raise ValueError("raw_sha256 inválido")
    if not SHA256_PATTERN.fullmatch(rows_sha256):
        raise ValueError("rows_sha256 inválido")
    rows = payload["rows"]
    row_count = payload["row_count"]
    if not isinstance(rows, list) or not isinstance(row_count, int):
        raise ValueError("rows o row_count inválido")
    if row_count != len(rows) or row_count < 0:
        raise ValueError("row_count no coincide con rows")
    if payload["schema_version"] == "1.2":
        for fila in rows:
            if not isinstance(fila, dict) or any(fila.get(c) in (None, "") for c in CAMPOS_1_2):
                raise ValueError("Schema 1.2: cada fila requiere " + ", ".join(CAMPOS_1_2))
        if es_solicitud:
            for fila in rows:
                date(int(fila["anio_documento"]), int(fila["mes_documento"]), int(fila["dia_documento"]))
    canonical_rows = json.dumps(
        rows,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    calculated_rows_sha256 = hashlib.sha256(canonical_rows).hexdigest()
    if not hmac.compare_digest(calculated_rows_sha256, rows_sha256):
        raise ValueError("rows_sha256 no coincide con rows")

    raw_size_bytes = payload["raw_file"]["size_bytes"]
    if not isinstance(raw_size_bytes, int) or raw_size_bytes < 0:
        raise ValueError("size_bytes inválido")
    return {
        "extraction_id": extraction_id,
        "solicitud_id": solicitud_id,
        "schema_version": payload["schema_version"],
        "source": payload["source"],
        "window_start": window_start,
        "window_end": window_end,
        "generated_at": generated_at,
        "raw_sha256": raw_sha256,
        "raw_size_bytes": raw_size_bytes,
        "rows_sha256": rows_sha256,
        "row_count": row_count,
    }


def _validate_cut(cut):
    """Corte que ya aplicó el extractor (schema 1.1): nombre y ventana (desde, hasta]."""
    if isinstance(cut, dict) and cut.get("nombre") == NOMBRE_SOLICITUD:
        desde, hasta = parse_date(str(cut.get("desde", ""))), parse_date(str(cut.get("hasta", "")))
        if desde is None or hasta is None or hasta < desde:
            raise ValueError("cut.desde/cut.hasta deben ser fechas AAAA-MM-DD válidas")
        return
    if not isinstance(cut, dict) or cut.get("nombre") not in NOMBRES_CUT:
        raise ValueError("cut.nombre inválido")
    desde = parse_datetime(str(cut.get("desde", "")))
    hasta = parse_datetime(str(cut.get("hasta", "")))
    if desde is None or hasta is None or desde.tzinfo is None or hasta.tzinfo is None:
        raise ValueError("cut.desde/cut.hasta deben ser fechas con zona horaria")
    if hasta <= desde:
        raise ValueError("cut.hasta debe ser posterior a cut.desde")


def _source_ip(request):
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",", 1)[0].strip() or request.META.get("REMOTE_ADDR")


def _error(code, status, detail=None):
    body = {"error": code}
    if detail:
        body["detail"] = detail
    return JsonResponse(body, status=status)
