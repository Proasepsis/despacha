import base64
import binascii
import json
from datetime import timedelta

from django.db.models import Count, Q
from django.http import HttpResponseNotModified, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_GET

from core.models import ParametroSalida
from cortes.models import Corte, Documento
from cortes.servicios.generar_archivo import construir_fila_salida

from .auth import autenticar_vigia


SCHEMA_VERSION = "1.0"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
DEFAULT_DOCUMENT_PAGE_SIZE = 200
MAX_DOCUMENT_PAGE_SIZE = 500


@require_GET
@autenticar_vigia
def listar_cortes(request):
    try:
        filters = _parse_filters(request)
    except ValueError as error:
        return JsonResponse({"error": "invalid_query", "detail": str(error)}, status=400)

    queryset = Corte.objects.filter(estado="generado")
    if filters["fecha_desde"]:
        queryset = queryset.filter(fecha__gte=filters["fecha_desde"])
    if filters["fecha_hasta"]:
        queryset = queryset.filter(fecha__lte=filters["fecha_hasta"])
    if filters["actualizado_desde"]:
        queryset = queryset.filter(actualizado_en__gte=filters["actualizado_desde"])
    if filters["cursor"]:
        cursor_time, cursor_id = filters["cursor"]
        queryset = queryset.filter(
            Q(actualizado_en__gt=cursor_time)
            | Q(actualizado_en=cursor_time, id__gt=cursor_id)
        )

    page_size = filters["page_size"]
    page_ids = list(
        queryset.order_by("actualizado_en", "id").values_list("id", flat=True)[
            : page_size + 1
        ]
    )
    has_more = len(page_ids) > page_size
    page_ids = page_ids[:page_size]
    cortes_map = {
        corte.id: corte
        for corte in Corte.objects.filter(id__in=page_ids).annotate(
            documento_count=Count("documentos", distinct=True),
            linea_count=Count("documentos__lineas", distinct=True),
        )
    }
    cortes = [cortes_map[corte_id] for corte_id in page_ids]
    next_cursor = _encode_cursor(cortes[-1]) if has_more else None

    response = JsonResponse(
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": timezone.now().isoformat(),
            "count": len(cortes),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "results": [_serialize_summary(corte, request) for corte in cortes],
        }
    )
    response["X-Schema-Version"] = SCHEMA_VERSION
    return response


@require_GET
@autenticar_vigia
def detalle_corte(request, corte_id):
    corte = Corte.objects.filter(pk=corte_id, estado="generado").first()
    if corte is None:
        return JsonResponse({"error": "not_found"}, status=404)

    latest_version = corte.versiones.order_by("-numero").first()
    entity_hash = latest_version.archivo_hash if latest_version else corte.hash_sha256
    etag = f'"{entity_hash}"'
    if request.headers.get("If-None-Match") == etag:
        return HttpResponseNotModified()

    try:
        document_params = _parse_document_params(request)
    except ValueError as error:
        return JsonResponse({"error": "invalid_query", "detail": str(error)}, status=400)

    documents_query = Documento.objects.filter(corte=corte).select_related("ciudad")
    if document_params["cursor"]:
        documents_query = documents_query.filter(id__gt=document_params["cursor"])
    documents_page = list(
        documents_query.prefetch_related("lineas").order_by("id")[
            : document_params["page_size"] + 1
        ]
    )
    documents_has_more = len(documents_page) > document_params["page_size"]
    documents_page = documents_page[: document_params["page_size"]]
    documents_next_cursor = (
        _encode_document_cursor(documents_page[-1].id) if documents_has_more else None
    )

    params = {item.clave: item.valor for item in ParametroSalida.objects.all()}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "data": {
            "id": corte.id,
            "fecha": corte.fecha.isoformat(),
            "numero_corte": corte.numero_corte,
            "adicional": corte.adicional_letra,
            "nombre": corte.display_corte,
            "version": corte.version_actual,
            "actualizado_en": corte.actualizado_en.isoformat(),
            "archivo_sha256": entity_hash,
            "documentos_has_more": documents_has_more,
            "documentos_next_cursor": documents_next_cursor,
            "documentos": [
                _serialize_document(documento, params) for documento in documents_page
            ],
        },
    }
    response = JsonResponse(payload)
    response["ETag"] = etag
    response["Cache-Control"] = "private, max-age=60"
    response["X-Schema-Version"] = SCHEMA_VERSION
    return response


def _parse_filters(request):
    fecha_desde = _optional_date(request.GET.get("fecha_desde"), "fecha_desde")
    fecha_hasta = _optional_date(request.GET.get("fecha_hasta"), "fecha_hasta")
    actualizado_desde = _optional_datetime(request.GET.get("actualizado_desde"))
    if fecha_desde and fecha_hasta and fecha_hasta < fecha_desde:
        raise ValueError("fecha_hasta no puede ser anterior a fecha_desde")
    if not fecha_desde and not fecha_hasta and not actualizado_desde:
        fecha_desde = timezone.localdate() - timedelta(days=30)

    raw_page_size = request.GET.get("page_size", str(DEFAULT_PAGE_SIZE))
    try:
        page_size = int(raw_page_size)
    except ValueError as error:
        raise ValueError("page_size debe ser un entero") from error
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page_size debe estar entre 1 y {MAX_PAGE_SIZE}")

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "actualizado_desde": actualizado_desde,
        "page_size": page_size,
        "cursor": _decode_cursor(request.GET.get("cursor")),
    }


def _optional_date(value, name):
    if not value:
        return None
    parsed = parse_date(value)
    if parsed is None:
        raise ValueError(f"{name} debe usar formato YYYY-MM-DD")
    return parsed


def _optional_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValueError("actualizado_desde debe ser ISO-8601")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _parse_document_params(request):
    raw_page_size = request.GET.get(
        "page_size", str(DEFAULT_DOCUMENT_PAGE_SIZE)
    )
    try:
        page_size = int(raw_page_size)
    except ValueError as error:
        raise ValueError("page_size debe ser un entero") from error
    if not 1 <= page_size <= MAX_DOCUMENT_PAGE_SIZE:
        raise ValueError(
            f"page_size debe estar entre 1 y {MAX_DOCUMENT_PAGE_SIZE}"
        )
    return {
        "page_size": page_size,
        "cursor": _decode_document_cursor(request.GET.get("documento_cursor")),
    }


def _encode_document_cursor(document_id):
    body = json.dumps([document_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(body).decode().rstrip("=")


def _decode_document_cursor(value):
    if not value:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        raw = json.loads(base64.urlsafe_b64decode(value + padding).decode())
        return int(raw[0])
    except (
        ValueError,
        TypeError,
        IndexError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        binascii.Error,
    ) as error:
        raise ValueError("documento_cursor invalido") from error


def _encode_cursor(corte):
    body = json.dumps(
        [corte.actualizado_en.isoformat(), corte.id], separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(body).decode().rstrip("=")


def _decode_cursor(value):
    if not value:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        raw_time, raw_id = json.loads(
            base64.urlsafe_b64decode(value + padding).decode()
        )
        parsed_time = parse_datetime(raw_time)
        if parsed_time is None:
            raise ValueError
        if timezone.is_naive(parsed_time):
            parsed_time = timezone.make_aware(parsed_time)
        return parsed_time, int(raw_id)
    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        binascii.Error,
    ) as error:
        raise ValueError("cursor invalido") from error


def _serialize_summary(corte, request):
    return {
        "id": corte.id,
        "fecha": corte.fecha.isoformat(),
        "numero_corte": corte.numero_corte,
        "adicional": corte.adicional_letra,
        "nombre": corte.display_corte,
        "version": corte.version_actual,
        "actualizado_en": corte.actualizado_en.isoformat(),
        "documentos": corte.documento_count,
        "lineas": corte.linea_count,
        "path": f"/api/v1/vigia/cortes/{corte.id}",
    }


def _serialize_document(documento, params):
    ciudad = documento.ciudad
    return {
        "id": documento.id,
        "factura": documento.factura,
        "tipo_comprobante": documento.tipo_comprobante,
        "nit": documento.nit,
        "sucursal": documento.sucursal,
        "ciudad": (
            {"codigo": ciudad.codigo, "nombre": ciudad.nombre} if ciudad else None
        ),
        "lineas": [
            {"id": linea.id, **construir_fila_salida(documento, linea, params)}
            for linea in documento.lineas.all()
        ],
    }
