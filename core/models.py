from django.db import models


class ParametroSalida(models.Model):
    clave = models.CharField(max_length=50, primary_key=True)
    valor = models.CharField(max_length=200)
    descripcion = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "Parámetro de salida"
        verbose_name_plural = "Parámetros de salida"

    def __str__(self):
        return f"{self.clave} = {self.valor}"


class ReglaClasificacion(models.Model):
    CAMPO_CHOICES = [
        ("clasificador1", "Clasificador 1 (Embalaje)"),
        ("observaciones", "Observaciones (Prioridad)"),
    ]

    nombre = models.CharField(max_length=100, unique=True)
    campo_destino = models.CharField(max_length=20, choices=CAMPO_CHOICES)
    valor_por_defecto = models.CharField(max_length=50)
    activa = models.BooleanField(default=True)
    prioridad = models.PositiveSmallIntegerField(default=100)

    class Meta:
        verbose_name = "Regla de clasificación"
        verbose_name_plural = "Reglas de clasificación"
        ordering = ["prioridad"]

    def __str__(self):
        return f"{self.nombre} → {self.campo_destino} = {self.valor_por_defecto}"


class NotificacionDestinatarios(models.Model):
    EVENTO_CHOICES = [
        ("corte_generado", "Corte generado"),
        ("corte_regenerado", "Corte regenerado"),
        ("sin_maestro_detectado", "Producto sin maestra detectado"),
    ]

    evento = models.CharField(max_length=50, primary_key=True, choices=EVENTO_CHOICES)
    correos = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Destinatario de notificación"
        verbose_name_plural = "Destinatarios de notificación"

    def __str__(self):
        return f"{self.get_evento_display()}"
