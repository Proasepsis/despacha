def limpiar_lote(lote_raw: str | None) -> str:
    """
    Aplica las reglas de limpieza de lote del adaptador PLANTILLA.
    Función pura: misma entrada, misma salida; sin efectos secundarios.

    Reglas, en este orden exacto:
    1. Comilla inicial: quitarla.
    2. Slash: cortar todo desde el / inclusive.
    3. Puntos al inicio: quitarlos.
    4. Espacios: quitar TODOS los espacios.
    5. Guion terminal solo: reemplazar por -1.
    6. El punto al final NO se agrega ni se quita. Se conserva.
    """
    if lote_raw is None:
        return ""

    lote = lote_raw

    # 1. Quitar comilla inicial
    if lote.startswith("'"):
        lote = lote[1:]

    # 2. Cortar desde el slash inclusive
    if "/" in lote:
        lote = lote.split("/")[0]

    # 3. Quitar puntos al inicio
    lote = lote.lstrip(".")

    # 4. Quitar TODOS los espacios
    lote = lote.replace(" ", "")

    # 5. Guion terminal solo → reemplazar por -1
    if lote.endswith("-") and len(lote) > 1:
        lote = lote + "1"

    # 6. El punto al final se conserva tal cual (no se agrega ni se quita)

    return lote
