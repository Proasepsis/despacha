from datetime import datetime
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")


def sugerir_corte(ahora: datetime | None = None) -> int:
    """
    Determina qué corte sugerir según la hora actual en Bogotá.
    Spec acordado: Corte 1 = mañana [00:00, 12:00), Corte 2 = tarde [12:00, 24:00).
    """
    if ahora is None:
        ahora = datetime.now(BOGOTA)
    elif ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=BOGOTA)
    else:
        ahora = ahora.astimezone(BOGOTA)
    return 1 if ahora.hour < 12 else 2
