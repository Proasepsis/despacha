import logging
import os

from django.core.mail import EmailMessage, get_connection
from django.conf import settings

from core.models import NotificacionDestinatarios

logger = logging.getLogger(__name__)


def _destinatarios(evento: str) -> list[str]:
    try:
        entry = NotificacionDestinatarios.objects.filter(
            evento=evento, activo=True
        ).first()
        if not entry or not entry.correos.strip():
            return []
        correos = [
            c.strip() for c in entry.correos.replace("\n", ",").split(",") if c.strip()
        ]
        return correos
    except Exception:
        return []


def _prefijo_asunto() -> str:
    env = os.environ.get("ENVIRONMENT", "production")
    if env == "staging":
        return "[STAGING] "
    return ""


def _enviar(destinatarios: list[str], asunto: str, cuerpo: str) -> bool:
    if not destinatarios:
        logger.info("Sin destinatarios para %s", asunto)
        return False

    try:
        connection = get_connection()
        message = EmailMessage(
            subject=asunto,
            body=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=destinatarios,
            connection=connection,
        )
        message.send(fail_silently=False)
        return True
    except Exception as e:
        logger.error("Fallo al enviar notificación '%s': %s", asunto, e)
        from core.servicios.auditoria import registrar

        try:
            registrar(
                usuario=None,
                objeto_tipo="Notificacion",
                objeto_id="0",
                tipo_evento="notificacion_fallida",
                campo=asunto,
                valor_nuevo=str(e),
            )
        except Exception:
            pass
        return False


def notificar_corte_generado(corte) -> bool:
    prefijo = _prefijo_asunto()
    asunto = f"{prefijo}Corte {corte.numero_corte} {corte.fecha:%d/%m/%Y} generado"

    ver = corte.version_actual
    drive_url = ""
    ultima_version = corte.versiones.order_by("-numero").first()
    if ultima_version:
        drive_url = ultima_version.drive_url

    cuerpo = (
        f"Corte {corte.numero_corte} del {corte.fecha:%d/%m/%Y} generado.\n\n"
        f"Versión: v{ver}\n"
        f"Total documentos: {corte.documentos.count()}\n"
    )
    if drive_url:
        cuerpo += f"Drive: {drive_url}\n"

    destinatarios = _destinatarios("corte_generado")
    return _enviar(destinatarios, asunto, cuerpo)


def notificar_corte_regenerado(corte) -> bool:
    prefijo = _prefijo_asunto()
    ver = corte.version_actual
    asunto = (
        f"{prefijo}ATENCIÓN: nueva versión v{ver} "
        f"del corte {corte.numero_corte} {corte.fecha:%d/%m/%Y}"
    )

    drive_url = ""
    ultima_version = corte.versiones.order_by("-numero").first()
    motivo = ultima_version.motivo if ultima_version else ""
    if ultima_version:
        drive_url = ultima_version.drive_url

    cuerpo = (
        f"ATENCIÓN: este archivo reemplaza al enviado previamente.\n\n"
        f"Corte {corte.numero_corte} del {corte.fecha:%d/%m/%Y}\n"
        f"Nueva versión: v{ver}\n"
    )
    if motivo:
        cuerpo += f"Motivo: {motivo}\n"
    if drive_url:
        cuerpo += f"Drive: {drive_url}\n"

    destinatarios = _destinatarios("corte_regenerado")
    return _enviar(destinatarios, asunto, cuerpo)


def notificar_sin_maestra_detectado(corte, productos_codigos: list[str]) -> bool:
    prefijo = _prefijo_asunto()
    asunto = (
        f"{prefijo}Productos sin maestra detectados "
        f"en corte {corte.numero_corte} {corte.fecha:%d/%m/%Y}"
    )

    cuerpo = (
        f"Se detectaron {len(productos_codigos)} código(s) sin producto en la maestra "
        f"en el corte {corte.numero_corte} del {corte.fecha:%d/%m/%Y}.\n\n"
        f"Códigos sin maestra:\n"
    )
    for codigo in productos_codigos:
        cuerpo += f"  - {codigo}\n"

    cuerpo += f"\nResuélvelo en el admin de productos.\n"

    destinatarios = _destinatarios("sin_maestro_detectado")
    return _enviar(destinatarios, asunto, cuerpo)
