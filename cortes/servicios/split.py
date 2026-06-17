from django.contrib.auth.models import User
from django.db import transaction

from cortes.models import Corte, Documento, Linea
from cortes.servicios.auditoria import registrar_auditoria

LETRAS_SUFIJO = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _siguiente_sufijo(corte: Corte, factura_original: str) -> str:
    existentes = set(
        Documento.objects.filter(
            corte=corte, factura__startswith=factura_original
        ).values_list("factura", flat=True)
    )

    for letra in LETRAS_SUFIJO:
        candidata = f"{factura_original}{letra}"
        if candidata not in existentes:
            return candidata

    raise ValueError(f"No hay sufijos disponibles para {factura_original}")


@transaction.atomic
def partir_documento(
    documento_origen: Documento,
    lineas_ids_a_mover: list[int],
    usuario: User,
) -> Documento:
    if documento_origen.corte.estado != "en_revision":
        raise ValueError("No se puede partir un documento en un corte que no está en revisión. Regenere si ya fue generado.")
    if not lineas_ids_a_mover:
        raise ValueError("Debe seleccionar al menos una línea para mover.")

    lineas = list(
        Linea.objects.filter(
            id__in=lineas_ids_a_mover,
            documento=documento_origen,
        )
    )
    if len(lineas) != len(lineas_ids_a_mover):
        raise ValueError("Algunas líneas no pertenecen al documento origen.")

    nueva_factura = _siguiente_sufijo(documento_origen.corte, documento_origen.factura)

    nuevo_doc = Documento.objects.create(
        corte=documento_origen.corte,
        factura=nueva_factura,
        nit=documento_origen.nit,
        tipo_comprobante=documento_origen.tipo_comprobante,
        ciudad=documento_origen.ciudad,
        clasificador1=documento_origen.clasificador1,
        observaciones=documento_origen.observaciones,
        creado_por_split_de=documento_origen,
    )

    for linea in lineas:
        linea.movida_desde = documento_origen
    Linea.objects.bulk_update(lineas, ["movida_desde"])

    Linea.objects.filter(
        id__in=[l.id for l in lineas]
    ).update(documento=nuevo_doc)

    registrar_auditoria(
        usuario=usuario,
        objeto_tipo="Documento",
        objeto_id=str(nuevo_doc.pk),
        tipo_evento="split",
        valor_anterior=f"Partido de {documento_origen.factura} (id={documento_origen.pk})",
        valor_nuevo=f"{len(lineas_ids_a_mover)} líneas movidas a {nueva_factura}",
    )

    return nuevo_doc


@transaction.atomic
def deshacer_split(documento_nuevo: Documento, usuario: User) -> None:
    if documento_nuevo.creado_por_split_de is None:
        raise ValueError("Este documento no fue creado por split.")

    if documento_nuevo.corte.estado != "en_revision":
        raise ValueError("No se puede deshacer split en cortes generados. Regenere.")

    original = documento_nuevo.creado_por_split_de

    lineas = list(documento_nuevo.lineas.all())
    for linea in lineas:
        linea.movida_desde = None
    Linea.objects.bulk_update(lineas, ["movida_desde"])

    Linea.objects.filter(
        id__in=[l.id for l in lineas]
    ).update(documento=original, movida_desde=None)

    factura_original = documento_nuevo.factura
    documento_nuevo.delete()

    registrar_auditoria(
        usuario=usuario,
        objeto_tipo="Documento",
        objeto_id=str(original.pk),
        tipo_evento="deshacer_split",
        valor_anterior=f"Deshecho split {factura_original} (id={documento_nuevo.pk})",
        valor_nuevo=f"{len(lineas)} líneas devueltas a {original.factura}",
    )
