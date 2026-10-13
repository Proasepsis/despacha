import time
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import FilaSiigo, SolicitudExtraccion

TIMEOUT_TOMADA = timedelta(minutes=20)
MAX_INTENTOS = 3
MAX_DIAS = 31
MAX_ESPERA = 30


def validar_rango(inicio: date, fin: date):
    if fin < inicio:
        raise ValueError("fecha_inicio debe ser menor o igual a fecha_fin")
    if inicio.year != fin.year:
        raise ValueError("El rango debe estar dentro del mismo año")
    if (fin - inicio).days + 1 > MAX_DIAS:
        raise ValueError(f"El rango no puede superar {MAX_DIAS} días")
    if fin > timezone.localdate():
        raise ValueError("El rango no puede incluir fechas futuras")


class SolicitudEnCurso(Exception):
    def __init__(self, solicitud):
        super().__init__(f"Ya hay una solicitud {solicitud.estado} para ese rango")
        self.solicitud = solicitud


def crear_solicitud(inicio: date, fin: date, usuario) -> SolicitudExtraccion:
    """Idempotente por rango: si ya hay una pendiente/tomada igual, no crea otra (SolicitudEnCurso)."""
    validar_rango(inicio, fin)
    activas = SolicitudExtraccion.objects.filter(
        fecha_inicio=inicio, fecha_fin=fin, estado__in=[SolicitudExtraccion.PENDIENTE, SolicitudExtraccion.TOMADA]
    )
    if (existente := activas.first()) is not None:
        raise SolicitudEnCurso(existente)
    try:
        with transaction.atomic():
            return SolicitudExtraccion.objects.create(fecha_inicio=inicio, fecha_fin=fin, creada_por=usuario)
    except IntegrityError:  # doble clic simultáneo: la restricción de la base de datos gana
        raise SolicitudEnCurso(activas.get())


def vencer_tomadas():
    """Una solicitud tomada sin estado final tras 20 min vuelve a pendiente; al 3er intento falla."""
    ahora = timezone.now()
    vencidas = SolicitudExtraccion.objects.filter(
        estado=SolicitudExtraccion.TOMADA, tomada_en__lt=ahora - TIMEOUT_TOMADA
    )
    vencidas.filter(intentos__gte=MAX_INTENTOS).update(
        estado=SolicitudExtraccion.FALLIDA, error="sin respuesta del agente", completada_en=ahora
    )
    vencidas.update(estado=SolicitudExtraccion.PENDIENTE)  # las que quedan (re-evalúa el filtro)


def tomar_siguiente() -> SolicitudExtraccion | None:
    """Toma la pendiente más antigua. El UPDATE condicional es atómico: si otra llamada la ganó, reintenta."""
    vencer_tomadas()
    while True:
        pk = (
            SolicitudExtraccion.objects.filter(estado=SolicitudExtraccion.PENDIENTE)
            .order_by("creada_en")
            .values_list("pk", flat=True)
            .first()
        )
        if pk is None:
            return None
        tomadas = SolicitudExtraccion.objects.filter(
            pk=pk, estado=SolicitudExtraccion.PENDIENTE
        ).update(
            estado=SolicitudExtraccion.TOMADA, tomada_en=timezone.now(), intentos=F("intentos") + 1
        )
        if tomadas:
            return SolicitudExtraccion.objects.get(pk=pk)


def tomar_esperando(espera: float) -> SolicitudExtraccion | None:
    """Long-poll: como tomar_siguiente, pero reintenta cada segundo hasta `espera` s (máx. MAX_ESPERA)."""
    limite = time.monotonic() + min(max(espera, 0), MAX_ESPERA)
    while True:
        solicitud = tomar_siguiente()
        if solicitud is not None or time.monotonic() >= limite:
            return solicitud
        time.sleep(1)


def _txt(valor) -> str:
    return "" if valor is None else str(valor).strip()


def _fecha_documento(fila) -> date:
    return date(int(fila["anio_documento"]), int(fila["mes_documento"]), int(fila["dia_documento"]))


@transaction.atomic
def reemplazar_filas(ingestion, desde: date, hasta: date):
    """Foto completa de [desde, hasta]: reemplaza las filas de los documentos recibidos y marca
    como no_presente_en_siigo los que Despacha tenía en el rango y no vinieron (no se borran)."""
    nuevas, claves = [], set()
    for fila in ingestion.payload["rows"]:
        clave = tuple(_txt(fila.get(k)) for k in ("tipo_comprobante", "codigo_comprobante", "numero_documento"))
        claves.add(clave)
        nuevas.append(
            FilaSiigo(
                tipo_comprobante=clave[0],
                codigo_comprobante=clave[1],
                numero_documento=clave[2],
                secuencia=_txt(fila.get("secuencia")),
                fecha_documento=_fecha_documento(fila),
                fila=fila,
                ingestion=ingestion,
            )
        )
    for clave in claves:
        FilaSiigo.objects.filter(
            tipo_comprobante=clave[0], codigo_comprobante=clave[1], numero_documento=clave[2]
        ).delete()
    FilaSiigo.objects.bulk_create(nuevas)
    # ponytail: marca en memoria por documento; si el volumen crece, hacerlo con un NOT IN en SQL
    ausentes = [
        pk
        for pk, *k in FilaSiigo.objects.filter(fecha_documento__range=(desde, hasta)).values_list(
            "pk", "tipo_comprobante", "codigo_comprobante", "numero_documento"
        )
        if tuple(k) not in claves
    ]
    FilaSiigo.objects.filter(pk__in=ausentes).update(no_presente_en_siigo=True)
