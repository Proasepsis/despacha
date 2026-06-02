from django.db import migrations


def crear_datos_iniciales(apps, schema_editor):
    ParametroSalida = apps.get_model("core", "ParametroSalida")

    parametros = [
        ("punto", "PROA", "Punto de venta en archivo de salida"),
        ("identificacion", "PROASEPSIS", "Identificación de la empresa en archivo de salida"),
        ("nombre", "PROASEPSIS", "Nombre de la empresa en archivo de salida"),
        ("direccion", "BOGOTA", "Dirección en archivo de salida"),
        ("tipo_doc_ref", "FACT", "Tipo de documento de referencia"),
        ("estado_articulo", "DISP", "Estado del artículo (disponible)"),
        ("ciudad_default", "BOGOTA", "Ciudad por defecto si no viene en el documento"),
    ]
    for clave, valor, descripcion in parametros:
        ParametroSalida.objects.create(clave=clave, valor=valor, descripcion=descripcion)


def crear_reglas_iniciales(apps, schema_editor):
    ReglaClasificacion = apps.get_model("core", "ReglaClasificacion")

    ReglaClasificacion.objects.create(
        nombre="clasificador1_default",
        campo_destino="clasificador1",
        valor_por_defecto="EMBALAR",
        activa=True,
        prioridad=100,
    )
    ReglaClasificacion.objects.create(
        nombre="observaciones_default",
        campo_destino="observaciones",
        valor_por_defecto="NO PRIORIDAD",
        activa=True,
        prioridad=100,
    )


def crear_destinatarios_default(apps, schema_editor):
    NotificacionDestinatarios = apps.get_model("core", "NotificacionDestinatarios")

    eventos = ["corte_generado", "corte_regenerado", "sin_maestro_detectado"]
    for evento in eventos:
        NotificacionDestinatarios.objects.get_or_create(
            evento=evento,
            defaults={"correos": "", "activo": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            crear_datos_iniciales, reverse_code=migrations.RunPython.noop
        ),
        migrations.RunPython(
            crear_reglas_iniciales, reverse_code=migrations.RunPython.noop
        ),
        migrations.RunPython(
            crear_destinatarios_default, reverse_code=migrations.RunPython.noop
        ),
    ]
