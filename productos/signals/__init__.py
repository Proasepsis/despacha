from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from productos.models import Producto


@receiver(post_save, sender=Producto)
def auditar_cambio_producto(sender, instance, created, update_fields, **kwargs):
    from core.servicios.auditoria import registrar

    if update_fields is not None and "unidad_empaque" not in update_fields and "activo" not in update_fields:
        return

    usuario = None

    if created:
        registrar(
            usuario=usuario,
            objeto_tipo="Producto",
            objeto_id=instance.producto,
            tipo_evento="creacion",
            campo="producto",
            valor_nuevo=instance.referencia,
        )
        return

    if hasattr(instance, "_pre_save_unidad_empaque"):
        valor_anterior = instance._pre_save_unidad_empaque
        if valor_anterior != instance.unidad_empaque:
            registrar(
                usuario=usuario,
                objeto_tipo="Producto",
                objeto_id=instance.producto,
                tipo_evento="edicion",
                campo="unidad_empaque",
                valor_anterior=valor_anterior,
                valor_nuevo=instance.unidad_empaque,
            )

    if hasattr(instance, "_pre_save_activo"):
        valor_anterior = instance._pre_save_activo
        if valor_anterior != instance.activo:
            registrar(
                usuario=usuario,
                objeto_tipo="Producto",
                objeto_id=instance.producto,
                tipo_evento="edicion",
                campo="activo",
                valor_anterior=valor_anterior,
                valor_nuevo=instance.activo,
            )


@receiver(post_delete, sender=Producto)
def auditar_eliminacion_producto(sender, instance, **kwargs):
    from core.servicios.auditoria import registrar

    registrar(
        usuario=None,
        objeto_tipo="Producto",
        objeto_id=instance.producto,
        tipo_evento="inactivacion",
        campo="producto",
        valor_anterior=instance.referencia,
    )
