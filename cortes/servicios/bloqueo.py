from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from cortes.models import Corte

TIMEOUT_BLOQUEO = timedelta(minutes=30)


@transaction.atomic
def intentar_tomar_bloqueo(corte: Corte, usuario: User) -> bool:
    corte.refresh_from_db()

    if corte.bloqueado_por_id and corte.bloqueado_por_id != usuario.pk:
        if corte.bloqueado_hasta and corte.bloqueado_hasta > timezone.now():
            return False

    corte.bloqueado_por = usuario
    corte.bloqueado_hasta = timezone.now() + TIMEOUT_BLOQUEO
    corte.save(update_fields=["bloqueado_por", "bloqueado_hasta"])
    return True


@transaction.atomic
def refrescar_bloqueo(corte: Corte, usuario: User) -> bool:
    corte.refresh_from_db()

    if corte.bloqueado_por_id != usuario.pk:
        return False

    if corte.bloqueado_hasta and corte.bloqueado_hasta < timezone.now():
        return False

    corte.bloqueado_hasta = timezone.now() + TIMEOUT_BLOQUEO
    corte.save(update_fields=["bloqueado_hasta"])
    return True


@transaction.atomic
def liberar_bloqueo(corte: Corte, usuario: User, forzado_por_admin: bool = False) -> None:
    from cortes.servicios.auditoria import registrar_auditoria

    corte.refresh_from_db()
    if not corte.bloqueado_por_id:
        return

    if forzado_por_admin:
        registrar_auditoria(
            usuario=usuario,
            objeto_tipo="Corte",
            objeto_id=str(corte.pk),
            tipo_evento="forzar_liberacion",
            valor_anterior=str(corte.bloqueado_por_id),
            valor_nuevo="",
        )

    corte.bloqueado_por = None
    corte.bloqueado_hasta = None
    corte.save(update_fields=["bloqueado_por", "bloqueado_hasta"])


def info_bloqueo(corte: Corte) -> dict | None:
    corte.refresh_from_db()
    if not corte.bloqueado_por_id:
        return None

    if corte.bloqueado_hasta and corte.bloqueado_hasta < timezone.now():
        corte.bloqueado_por = None
        corte.bloqueado_hasta = None
        corte.save(update_fields=["bloqueado_por", "bloqueado_hasta"])
        return None

    username = (
        User.objects.values_list("username", flat=True)
        .filter(pk=corte.bloqueado_por_id)
        .first()
        or ""
    )
    return {
        "usuario": username,
        "usuario_id": corte.bloqueado_por_id,
        "desde": corte.bloqueado_hasta - TIMEOUT_BLOQUEO,
        "hasta": corte.bloqueado_hasta,
    }
