from django.db import migrations


def crear_ciudad_bogota(apps, schema_editor):
    Ciudad = apps.get_model("productos", "Ciudad")
    Ciudad.objects.create(
        codigo="11001",
        nombre="Bogotá D.C.",
        nombre_archivo="BOGOTA",
        activo=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("productos", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            crear_ciudad_bogota, reverse_code=migrations.RunPython.noop
        ),
    ]
