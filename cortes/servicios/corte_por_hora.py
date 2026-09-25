from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")


def sugerir_corte(ahora: datetime | None = None) -> int:
    """
    Determina qué corte sugerir según la hora actual en Bogotá.
    Corte 2 = mañana [00:00, 12:00), Corte 1 = tarde [12:00, 24:00).
    """
    if ahora is None:
        ahora = datetime.now(BOGOTA)
    elif ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=BOGOTA)
    else:
        ahora = ahora.astimezone(BOGOTA)
    return 2 if ahora.hour < 12 else 1


# Franjas de facturación (hora de actualización del documento en SIIGO, Bogotá):
# Corte 2 = [16:00 del día anterior, 11:00), Corte 1 = [11:00, 16:00).
HORA_INICIO_CORTE_1 = time(11, 0)
HORA_FIN_CORTE_1 = time(16, 0)


def ventana_corte(fecha: date, numero_corte: int) -> tuple[datetime, datetime]:
    """Devuelve (inicio incluido, fin excluido) en hora local de Bogotá, sin tz."""
    if numero_corte == 2:
        return (
            datetime.combine(fecha - timedelta(days=1), HORA_FIN_CORTE_1),
            datetime.combine(fecha, HORA_INICIO_CORTE_1),
        )
    return (
        datetime.combine(fecha, HORA_INICIO_CORTE_1),
        datetime.combine(fecha, HORA_FIN_CORTE_1),
    )
