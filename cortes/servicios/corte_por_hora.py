from datetime import datetime
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")


def sugerir_corte(ahora: datetime | None = None) -> int:
    """
    Determina qué corte sugerir según la hora actual en Bogotá.
    Corte 1: [00:00, 12:00). Corte 2: [12:00, 24:00).
    Las 12:00 en punto pertenecen al Corte 2.
    """
    if ahora is None:
        ahora = datetime.now(BOGOTA)
    elif ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=BOGOTA)
    else:
        ahora = ahora.astimezone(BOGOTA)
    return 1 if ahora.hour < 12 else 2
