from django.db import migrations
from django.contrib.contenttypes.management import create_contenttypes


def crear_grupos(apps, schema_editor):
    # Ensure content types and permissions exist before querying them.
    # Django creates Permission objects via post_migrate, which fires after all
    # migrations complete — so RunPython migrations must trigger this manually.
    for app_config in apps.get_app_configs():
        if app_config.label in ("cortes", "core", "productos"):
            create_contenttypes(app_config, verbosity=0)
    from django.contrib.auth.management import create_permissions
    for app_config in apps.get_app_configs():
        if app_config.label in ("cortes", "core", "productos"):
            create_permissions(app_config, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    grupo_facturacion, _ = Group.objects.get_or_create(name="facturacion")
    grupo_almacenamiento, _ = Group.objects.get_or_create(name="almacenamiento")

    perms_facturacion = set()
    for perm in Permission.objects.filter(
        content_type__app_label__in=["cortes", "core", "productos"],
        codename__startswith="view",
    ):
        perms_facturacion.add(perm)
    for perm in Permission.objects.filter(
        content_type__app_label="cortes",
        content_type__model="corte",
        codename__in=["add_corte", "change_corte"],
    ):
        perms_facturacion.add(perm)
    grupo_facturacion.permissions.set(perms_facturacion)

    perms_almacenamiento = set()
    for perm in Permission.objects.filter(
        content_type__app_label__in=["cortes", "core", "productos"],
        codename__startswith="view",
    ):
        perms_almacenamiento.add(perm)
    for codename, model in [
        ("change_documento", "documento"),
        ("change_linea", "linea"),
        ("add_corteversion", "corteversion"),
        ("change_corte", "corte"),
    ]:
        for perm in Permission.objects.filter(
            content_type__app_label="cortes",
            content_type__model=model,
            codename=codename,
        ):
            perms_almacenamiento.add(perm)
    grupo_almacenamiento.permissions.set(perms_almacenamiento)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_grupos"),
        ("cortes", "0003_documento_novedad"),
    ]

    operations = [
        migrations.RunPython(crear_grupos, reverse_code=migrations.RunPython.noop),
    ]
