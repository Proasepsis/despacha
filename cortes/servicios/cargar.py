import hashlib
import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction, IntegrityError

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


class ErrorSugerirAdicional(ErrorCarga):
    def __init__(self, numero_corte: int, fecha: date):
        self.numero_corte = numero_corte
        self.fecha = fecha
        super().__init__(
            f"Ya existe Corte {numero_corte} para el {fecha:%d/%m/%Y}. "
            "Si es un cargue adicional, marca la casilla «Es adicional» e intenta de nuevo."
        )


_LETRAS_ADICIONALES = "ABCDE"


def _siguiente_letra_adicional(fecha_corte: date, numero_corte: int) -> str:
    usadas = set(
        Corte.objects.filter(fecha=fecha_corte, numero_corte=numero_corte)
        .exclude(adicional_letra="")
        .values_list("adicional_letra", flat=True)
    )
    for letra in _LETRAS_ADICIONALES:
        if letra not in usadas:
            return letra
    raise ErrorCarga(
        f"Se alcanzó el límite de {len(_LETRAS_ADICIONALES)} cortes adicionales para este corte."
    )


@transaction.atomic
def cargar_archivo(
    archivo: UploadedFile,
    usuario: User,
    formato_origen: str,
    numero_corte: int,
    es_adicional: bool = False,
    tipo_comprobante: str = "",
    fecha: date | None = None,
) -> tuple[Corte, ResultadoProcesamiento]:
    contenido = archivo.read()
    archivo.seek(0)

    hash_sha256 = hashlib.sha256(contenido).hexdigest()

    existente = Corte.objects.filter(hash_sha256=hash_sha256).first()
    if existente:
        raise ErrorDuplicado(corte_existente_id=existente.pk)

    fecha_corte = fecha or date.today()

    if not es_adicional:
        if Corte.objects.filter(fecha=fecha_corte, numero_corte=numero_corte, adicional_letra="").exists():
            raise ErrorSugerirAdicional(numero_corte, fecha_corte)

    adicional_letra = _siguiente_letra_adicional(fecha_corte, numero_corte) if es_adicional else ""

    try:
        with transaction.atomic():
            corte = Corte.objects.create(
                archivo=archivo.name,
                formato_origen=formato_origen,
                hash_sha256=hash_sha256,
                usuario_carga=usuario,
                fecha=fecha_corte,
                numero_corte=numero_corte,
                adicional_letra=adicional_letra,
                estado="cargado",
            )
    except IntegrityError:
        if not es_adicional:
            raise ErrorSugerirAdicional(numero_corte, fecha_corte)
        raise ErrorCombinacionFechaCorte(
            f"Ya existe Corte {numero_corte}{adicional_letra} para el {fecha_corte:%d/%m/%Y}."
        )

    suffix = Path(archivo.name).suffix or ".xlsx"
    fd, tmp_path_str = tempfile.mkstemp(suffix=suffix)
    tmp_path = Path(tmp_path_str)
    try:
        with open(fd, "wb") as f:
            f.write(contenido)

        try:
            adaptador = obtener_adaptador(formato_origen)
            adaptador.validar(tmp_path)
        except Exception as e:
            corte.delete()
            raise ErrorValidacionAdaptador(str(e)) from e

        documentos = adaptador.parse(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    existente_combinacion = Corte.objects.filter(
        fecha=corte.fecha,
        numero_corte=numero_corte,
        adicional_letra=corte.adicional_letra,
    ).exclude(pk=corte.pk).first()
    if existente_combinacion:
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
