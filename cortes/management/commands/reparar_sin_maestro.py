from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.adaptadores.api_siigo.convertir import filas_a_documentos_internos
from core.adaptadores.plantilla.limpieza import limpiar_lote
from cortes.models import Corte, Linea
from integraciones_siigo.models import IngestionSiigo
from productos.models import Producto


class Command(BaseCommand):
    help = "Re-resuelve las líneas sin_maestro de un corte SIIGO contra la maestra actual, usando su ingesta."

    def add_arguments(self, parser):
        parser.add_argument("corte_id", type=int)
        parser.add_argument("--aplicar", action="store_true", help="Sin esto solo muestra qué cambiaría")

    @transaction.atomic
    def handle(self, corte_id, aplicar, **kw):
        corte = Corte.objects.get(pk=corte_id)
        if corte.estado != "en_revision":
            raise CommandError(f"El corte está '{corte.estado}'; solo se repara en_revision.")
        eid = corte.archivo.removeprefix("siigo-").removesuffix(".json")
        ing = IngestionSiigo.objects.filter(extraction_id=eid).first()
        if not ing:
            raise CommandError(f"No hay ingesta para '{corte.archivo}'.")

        # (tipo, codigo, factura) -> líneas internas ya resolubles, con su código de producto
        internas = {}
        for d in filas_a_documentos_internos(ing.payload.get("rows", [])):
            internas[(d.tipo_comprobante, d.codigo_comprobante, d.factura)] = d.lineas
        productos = {p.producto: p for p in Producto.objects.filter(
            producto__in={l.producto_codigo for ls in internas.values() for l in ls if l.producto_codigo})}

        pendientes = Linea.objects.filter(documento__corte=corte, sin_maestro=True).select_related(
            "documento", "movida_desde")
        reparadas = 0
        for lin in pendientes:
            doc = lin.movida_desde or lin.documento  # ponytail: líneas partidas se buscan en el doc original
            for i in internas.get((doc.tipo_comprobante, doc.codigo_comprobante, doc.factura), []):
                p = productos.get(i.producto_codigo)
                desc = i.descripcion_origen.strip()
                if (p and limpiar_lote(i.lote_raw) == lin.lote and i.cantidad_origen == lin.cantidad_origen
                        and lin.descripcion_snapshot.endswith(desc)):
                    lin.referencia = lin.referencia_snapshot = p.referencia
                    lin.descripcion_snapshot = p.descripcion
                    lin.unidad_empaque_snapshot = p.unidad_empaque
                    lin.cantidad_unidades = round(lin.cantidad_origen * p.unidad_empaque)
                    lin.sin_maestro, lin.inactivo = False, not p.activo
                    self.stdout.write(f"{doc.factura}: línea {lin.pk} -> {p.producto} {p.referencia}")
                    if aplicar:
                        lin.save()
                    reparadas += 1
                    break
        restantes = pendientes.count() - (reparadas if aplicar else 0)
        self.stdout.write(f"{'Reparadas' if aplicar else 'Se repararían'}: {reparadas}. Siguen sin maestra: {restantes - (0 if aplicar else reparadas)}.")
