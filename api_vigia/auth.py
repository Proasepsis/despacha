import hashlib
import hmac
import ipaddress
import logging
from datetime import timedelta
from functools import wraps

from django.http import JsonResponse
from django.utils import timezone

from .models import CredencialVigia


logger = logging.getLogger(__name__)

USAGE_REFRESH_INTERVAL = timedelta(seconds=30)
PROXIES_CONFIABLES = {"127.0.0.1", "::1"}


def autenticar_vigia(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return _unauthorized()

        token = authorization.removeprefix("Bearer ").strip()
        parts = token.split("_", 2)
        if len(parts) != 3 or parts[0] != "vigia":
            return _unauthorized()

        credential = CredencialVigia.objects.filter(
            identificador=parts[1], activo=True
        ).first()
        if credential is None:
            return _unauthorized()

        received_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(received_hash, credential.token_sha256):
            return _unauthorized()

        source_ip = _source_ip(request)
        if not _ip_allowed(source_ip, credential.ips_permitidas):
            logger.warning(
                "Acceso API Vigia rechazado por IP: credential=%s ip=%s",
                credential.identificador,
                source_ip,
            )
            return JsonResponse({"error": "forbidden"}, status=403)

        now = timezone.now()
        refresh_cutoff = now - USAGE_REFRESH_INTERVAL
        CredencialVigia.objects.filter(pk=credential.pk).exclude(
            ultimo_uso_en__gte=refresh_cutoff
        ).update(
            ultimo_uso_en=now,
            ultima_ip=source_ip,
        )
        request.credencial_vigia = credential
        logger.info(
            "Acceso API Vigia: credential=%s ip=%s path=%s",
            credential.identificador,
            source_ip,
            request.path,
        )
        return view(request, *args, **kwargs)

    return wrapped


def _source_ip(request):
    remote_address = request.META.get("REMOTE_ADDR")
    forwarded_ip = request.headers.get("X-Real-IP")
    if remote_address in PROXIES_CONFIABLES and forwarded_ip:
        return forwarded_ip
    return remote_address


def _ip_allowed(source_ip, allowed_networks):
    if not allowed_networks:
        return True
    try:
        address = ipaddress.ip_address(source_ip)
        return any(
            address in ipaddress.ip_network(value, strict=False)
            for value in allowed_networks
        )
    except (TypeError, ValueError):
        return False


def _unauthorized():
    response = JsonResponse({"error": "unauthorized"}, status=401)
    response["WWW-Authenticate"] = "Bearer"
    return response
