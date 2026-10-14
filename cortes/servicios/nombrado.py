MESES_ABREV = [
    "ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
    "JUL", "AGO", "SEP", "OCT", "NOV", "DIC",
]


def nombre_archivo_corte(corte, siguiente_version: int | None = None) -> str:
    mes = MESES_ABREV[corte.fecha.month - 1]
    base = f"{mes} {corte.fecha.day} corte {corte.numero_corte}"

    version = siguiente_version if siguiente_version is not None else corte.version_actual + 1
    if version > 1:
        base += f" (v{version})"

    return base + ".xls"
