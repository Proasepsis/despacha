import re
from pathlib import Path

from django.core.management.base import BaseCommand

from clientes.models import Cliente


def _normalizar_nit(nit_raw: str) -> str:
    return re.sub(r"[.\-\s]", "", nit_raw.strip())


class Command(BaseCommand):
    help = "Importa la maestra de clientes desde un archivo CSV delimitado por punto y coma."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str, help="Ruta al archivo CSV")

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
                if not linea or num_linea == 1:
                    continue

                partes = [p.strip() for p in linea.split(";")]
                if len(partes) < 16:
                    errores.append(f"Línea {num_linea}: {len(partes)} columnas (esperadas >=16)")
                    continue

                nit_raw = partes[0]
                nit_clean = _normalizar_nit(nit_raw)

                if not nit_clean:
                    errores.append(f"Línea {num_linea}: NIT vacío tras normalizar '{nit_raw}'")
                    continue

                try:
                    cliente, created = Cliente.objects.update_or_create(
                        nit=nit_clean,
                        defaults={
                            "sucursal": partes[1][:20],
                            "dv": partes[2][:5],
                            "nombre": partes[3][:200],
                            "tipo": partes[4][:5],
                            "direccion": partes[5][:200],
                            "ciudad": partes[6][:100],
                            "fax": partes[7][:20],
                            "telefono_1": partes[8][:20],
                            "telefono_2": partes[9][:20],
                            "telefono_3": partes[10][:20],
                            "telefono_4": partes[11][:20],
                            "apartado": partes[12][:20],
                            "clasificacion": partes[13][:50],
                            "forma_pago": partes[14][:20],
                            "dia": partes[15][:10],
                        },
                    )
                    if created:
                        creados += 1
                    else:
                        actualizados += 1

                except Exception as e:
                    errores.append(f"Línea {num_linea}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Importación completa: {creados} creados, {actualizados} actualizados, {len(errores)} errores"
        ))

        if errores:
            for e in errores[:20]:
                self.stderr.write(self.style.WARNING(e))
