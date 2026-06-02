from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

from core.servicios.auditoria import registrar


@receiver(user_login_failed)
def auditar_login_fallido(sender, credentials, request, **kwargs):
    username = credentials.get("username", "desconocido")
    ip = _obtener_ip(request)
    registrar(
        usuario=None,
        objeto_tipo="User",
        objeto_id=username,
        tipo_evento="login_fallido",
        metadata={"ip": ip},
    )


def _obtener_ip(request) -> str:
    if request is None:
        return ""
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
