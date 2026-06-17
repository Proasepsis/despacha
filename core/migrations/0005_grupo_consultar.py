from django.db import migrations


def crear_grupo_consultar(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="consultar")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_grupos_nuevos"),
    ]

    operations = [
        migrations.RunPython(crear_grupo_consultar, reverse_code=migrations.RunPython.noop),
    ]
