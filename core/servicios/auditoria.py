from typing import Any

from django.contrib.auth.models import User
from cortes.models import Auditoria


def registrar(
    *,
    usuario: User,
    objeto_tipo: str,
    objeto_id: str | int,
    tipo_evento: str,
    campo: str = "",
    valor_anterior: Any = None,
    valor_nuevo: Any = None,
    metadata: dict | None = None,
) -> Auditoria:
    return Auditoria.objects.create(
        usuario=usuario,
        objeto_tipo=objeto_tipo,
        objeto_id=str(objeto_id),
        campo=campo,
        valor_anterior=_a_str(valor_anterior),
        valor_nuevo=_a_str(valor_nuevo),
        tipo_evento=tipo_evento,
        metadata=metadata or {},
    )


def _a_str(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor)
