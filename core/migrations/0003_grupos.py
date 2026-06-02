from django.db import migrations


def crear_grupos_y_permisos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    grupo_operario, _ = Group.objects.get_or_create(name="operario")
    grupo_consulta, _ = Group.objects.get_or_create(name="consulta")
    grupo_admin, _ = Group.objects.get_or_create(name="admin")

    permisos_todos = Permission.objects.all()
    grupo_admin.permissions.set(permisos_todos)

    permisos_consulta = Permission.objects.filter(
        content_type__app_label__in=["core", "productos", "cortes"],
        codename__startswith="view",
    )
    grupo_consulta.permissions.set(permisos_consulta)

    permisos_operario = set()

    for perm in Permission.objects.filter(
        content_type__app_label__in=["core", "productos", "cortes"],
    ):
        if perm.content_type.model in ("corte", "documento", "linea") and perm.codename in (
            "add_corte",
            "change_corte",
            "add_documento",
            "change_documento",
            "add_linea",
            "change_linea",
        ):
            permisos_operario.add(perm)

    for perm in Permission.objects.filter(
        content_type__app_label__in=["core", "productos", "cortes"],
        codename__startswith="view",
    ):
        permisos_operario.add(perm)

    grupo_operario.permissions.set(permisos_operario)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_datos_iniciales"),
        ("productos", "0002_ciudad_inicial"),
        ("cortes", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            crear_grupos_y_permisos, reverse_code=migrations.RunPython.noop
        ),
    ]
