import hashlib
import ipaddress
import secrets
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from api_vigia.models import CredencialVigia


class Command(BaseCommand):
    help = "Crea o rota una credencial de solo lectura para la API Vigia"

    def add_arguments(self, parser):
        parser.add_argument("nombre")
        parser.add_argument("--ip", action="append", default=[])
        parser.add_argument(
            "--permitir-cualquier-ip",
            action="store_true",
            help="Permite acceso desde cualquier IP (desaconsejado en produccion)",
        )
        parser.add_argument("--rotar", action="store_true")

    def handle(self, *args, **options):
        nombre = options["nombre"].strip()
        if not nombre:
            raise CommandError("El nombre no puede estar vacio")

        redes = []
        for raw_ip in options["ip"]:
            try:
                redes.append(str(ipaddress.ip_network(raw_ip, strict=False)))
            except ValueError as error:
                raise CommandError(f"IP o red invalida: {raw_ip}") from error
        if not redes and not options["permitir_cualquier_ip"]:
            raise CommandError(
                "Indique al menos una IP con --ip o use --permitir-cualquier-ip"
            )

        identifier = uuid.uuid4().hex[:16]
        token = f"vigia_{identifier}_{secrets.token_urlsafe(32)}"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        values = {
            "identificador": identifier,
            "token_sha256": token_hash,
            "ips_permitidas": redes,
            "activo": True,
            "ultimo_uso_en": None,
            "ultima_ip": None,
        }

        try:
            with transaction.atomic():
                credential = CredencialVigia.objects.select_for_update().filter(
                    nombre=nombre
                ).first()
                if credential and not options["rotar"]:
                    raise CommandError(
                        "La credencial ya existe; use --rotar para reemplazarla"
                    )
                if credential:
                    for field, value in values.items():
                        setattr(credential, field, value)
                    credential.save(update_fields=[*values])
                else:
                    CredencialVigia.objects.create(nombre=nombre, **values)
        except IntegrityError as error:
            raise CommandError("Otra ejecución creó la credencial al mismo tiempo") from error

        self.stdout.write(token)
