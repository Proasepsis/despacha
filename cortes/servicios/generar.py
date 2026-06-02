import hashlib

from django.db import transaction

from cortes.models import Corte, CorteVersion
from cortes.servicios.generar_archivo import generar_xls
from cortes.servicios.nombrado import nombre_archivo_corte
from cortes.servicios.auditoria import registrar_auditoria
from core.adaptadores.destinos.registry import DESTINOS_DISPONIBLES
from core.servicios.notificaciones import notificar_corte_generado, notificar_corte_regenerado


@transaction.atomic
def generar_y_entregar(
    corte: Corte,
    destinos: list[str],
    usuario,
    motivo: str = "",
) -> dict:
    corte.refresh_from_db()

    if corte.documentos.filter(lineas__sin_maestro=True).exists():
        raise ValueError(
            "No se puede generar: hay líneas sin producto en la maestra."
        )

    if not destinos:
        raise ValueError("Debe seleccionar al menos un destino.")

    for clave in destinos:
        if clave not in DESTINOS_DISPONIBLES:
            raise ValueError(f"Destino desconocido: {clave}")

    archivo_bytes = generar_xls(corte)

    siguiente_version = corte.version_actual + 1
    nombre = nombre_archivo_corte(corte, siguiente_version)
    archivo_hash = hashlib.sha256(archivo_bytes).hexdigest()

    resultados: dict[str, dict] = {}
    errores = []

    for clave in destinos:
        adaptador = DESTINOS_DISPONIBLES[clave]()
        resultado = adaptador.entregar(archivo_bytes, nombre, corte)

        resultados[clave] = {
            "ok": resultado.ok,
            "referencia": resultado.referencia,
            "error": resultado.error,
        }

        if not resultado.ok:
            errores.append(f"{clave}: {resultado.error}")

    if errores:
        corte.estado = "con_error"
        corte.save(update_fields=["estado"])
        return {
            "success": False,
            "resultados": resultados,
            "archivo_bytes": archivo_bytes,
            "nombre_archivo": nombre,
            "version": siguiente_version,
            "errores": errores,
        }

    corte.version_actual = siguiente_version
    corte.estado = "generado"
    corte.save(update_fields=["version_actual", "estado"])

    version = CorteVersion.objects.create(
        corte=corte,
        numero=siguiente_version,
        drive_url=resultados.get("drive", {}).get("referencia", ""),
        archivo_hash=archivo_hash,
        usuario=usuario,
        motivo=motivo,
    )

    tipo_evento = "regeneracion" if siguiente_version > 1 else "creacion"
    registrar_auditoria(
        usuario=usuario,
        objeto_tipo="Corte",
        objeto_id=str(corte.pk),
        tipo_evento=tipo_evento,
        campo="generacion",
        valor_anterior=str(siguiente_version - 1),
        valor_nuevo=str(siguiente_version),
    )

    if siguiente_version == 1:
        notificar_corte_generado(corte)
    else:
        notificar_corte_regenerado(corte)

    return {
        "success": True,
        "resultados": resultados,
        "archivo_bytes": archivo_bytes,
        "nombre_archivo": nombre,
        "version": siguiente_version,
        "errores": [],
    }
