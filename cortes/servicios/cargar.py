import hashlib
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.conf import settings

from cortes.models import Corte
from cortes.servicios.procesar import procesar_documentos_internos, ResultadoProcesamiento
from core.adaptadores.registry import obtener as obtener_adaptador
from core.servicios.notificaciones import notificar_sin_maestra_detectado


class ErrorCarga(Exception):
    pass


class ErrorDuplicado(ErrorCarga):
    def __init__(self, corte_existente_id: int):
        self.corte_existente_id = corte_existente_id
        super().__init__(f"Ya existe un corte con este archivo (id={corte_existente_id})")


class ErrorValidacionAdaptador(ErrorCarga):
    pass


class ErrorCombinacionFechaCorte(ErrorCarga):
    pass


@transaction.atomic
def cargar_archivo(
    archivo: UploadedFile,
    usuario: User,
    formato_origen: str,
    numero_corte: int,
    adicional_letra: str = "",
    fecha: date | None = None,
) -> tuple[Corte, ResultadoProcesamiento]:
    contenido = archivo.read()
    archivo.seek(0)

    hash_sha256 = hashlib.sha256(contenido).hexdigest()

    existente = Corte.objects.filter(hash_sha256=hash_sha256).first()
    if existente:
        raise ErrorDuplicado(corte_existente_id=existente.pk)

    uploads_dir = Path(settings.MEDIA_ROOT) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    ruta_guardado = uploads_dir / f"{hash_sha256}_{archivo.name}"
    with open(ruta_guardado, "wb") as f:
        f.write(contenido)

    corte = Corte.objects.create(
        archivo=archivo.name,
        formato_origen=formato_origen,
        hash_sha256=hash_sha256,
        usuario_carga=usuario,
        fecha=fecha or date.today(),
        numero_corte=numero_corte,
        adicional_letra=adicional_letra.upper() if adicional_letra else "",
        estado="cargado",
    )

    try:
        adaptador = obtener_adaptador(formato_origen)
        adaptador.validar(ruta_guardado)
    except Exception as e:
        corte.delete()
        raise ErrorValidacionAdaptador(str(e)) from e

    documentos = adaptador.parse(ruta_guardado)

    existente_combinacion = Corte.objects.filter(
        fecha=corte.fecha,
        numero_corte=numero_corte,
        adicional_letra=corte.adicional_letra,
    ).first()
    if existente_combinacion and existente_combinacion.pk != corte.pk:
        corte.delete()
        raise ErrorCombinacionFechaCorte(
            f"Ya existe {corte.display_corte} para el {corte.fecha}"
        )

    try:
        resultado = procesar_documentos_internos(corte, documentos)
    except Exception:
        corte.estado = "con_error"
        corte.save(update_fields=["estado"])
        raise

    corte.estado = "en_revision"
    corte.save(update_fields=["estado", "fecha"])

    if resultado.productos_nuevos_detectados:
        notificar_sin_maestra_detectado(corte, resultado.productos_nuevos_detectados)

    return corte, resultado
