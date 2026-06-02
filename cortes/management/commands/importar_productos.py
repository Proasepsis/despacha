from django.core.management.base import BaseCommand
from pathlib import Path

from productos.models import Producto


class Command(BaseCommand):
    help = "Importa la maestra de productos desde un archivo TSV."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str, help="Ruta al archivo TSV")
        parser.add_argument("--desde-interfase", action="store_true",
                          help="Modo refresco masivo: marca existentes como revisado, nuevos como no revisado")

    def handle(self, *args, **options):
        ruta = Path(options["archivo"])
        if not ruta.exists():
            self.stderr.write(self.style.ERROR(f"Archivo no encontrado: {ruta}"))
            return

        creados = 0
        actualizados = 0
        errores = []

        with open(ruta, encoding="utf-8") as f:
            for num_linea, linea in enumerate(f, start=1):
                linea = linea.strip()
                if not linea or linea.startswith("PRODUCTO"):
                    continue

                partes = linea.split("\t")
                if len(partes) < 7:
                    errores.append(f"Línea {num_linea}: {len(partes)} columnas (esperadas 7)")
                    continue

                try:
                    codigo = partes[0].strip()
                    descripcion = partes[1].strip()[:200]
                    referencia = partes[2].strip()[:50]
                    unidad_empaque_str = partes[6].strip()
                    unidad_empaque = int(float(unidad_empaque_str))

                    if len(codigo) != 13 or not codigo.isdigit():
                        errores.append(f"Línea {num_linea}: código inválido '{codigo}'")
                        continue

                    producto, created = Producto.objects.update_or_create(
                        producto=codigo,
                        defaults={
                            "referencia": referencia,
                            "descripcion": descripcion,
                            "unidad_empaque": unidad_empaque,
                            "activo": True,
                            "revisado": not options["desde_interfase"],
                        },
                    )
                    if created:
                        creados += 1
                    else:
                        producto.revisado = True
                        producto.save(update_fields=["revisado"])
                        actualizados += 1

                except (ValueError, IndexError) as e:
                    errores.append(f"Línea {num_linea}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Importación completa: {creados} nuevos, {actualizados} actualizados, {len(errores)} errores"
        ))

        if errores:
            for e in errores[:20]:
                self.stderr.write(self.style.WARNING(e))
