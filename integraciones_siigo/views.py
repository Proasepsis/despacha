import hashlib
import hmac
import json
import re
import uuid

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import IngestionSiigo


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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
        ingestion, created = IngestionSiigo.objects.get_or_create(
            extraction_id=validated.pop("extraction_id"),
            defaults={
                **validated,
                "content_sha256": body_hash,
                "payload": payload,
                "source_ip": _source_ip(request),
            },
        )
        if not created:
            if not hmac.compare_digest(ingestion.content_sha256, body_hash):
                return _error("idempotency_conflict", 409)
            return JsonResponse(
                {
                    "extraction_id": str(ingestion.extraction_id),
                    "raw_sha256": ingestion.raw_sha256,
                    "status": "duplicate",
                },
                status=200,
            )

    return JsonResponse(
        {
            "extraction_id": str(ingestion.extraction_id),
            "raw_sha256": ingestion.raw_sha256,
            "status": "accepted",
        },
        status=202,
    )


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
    if payload["schema_version"] != "1.0":
        raise ValueError("schema_version no soportada")
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


def _source_ip(request):
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",", 1)[0].strip() or request.META.get("REMOTE_ADDR")


def _error(code, status, detail=None):
    body = {"error": code}
    if detail:
        body["detail"] = detail
    return JsonResponse(body, status=status)
