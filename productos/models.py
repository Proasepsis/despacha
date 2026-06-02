from django.db import models


class Producto(models.Model):
    producto = models.CharField(max_length=13, primary_key=True)
    referencia = models.CharField(max_length=50, db_index=True)
    descripcion = models.CharField(max_length=200)
    unidad_empaque = models.PositiveIntegerField(default=1)
    activo = models.BooleanField(default=True)
    revisado = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["referencia"]
        indexes = [
            models.Index(fields=["activo", "revisado"]),
        ]

    def __str__(self):
        return f"{self.referencia} — {self.descripcion}"


class Ciudad(models.Model):
    codigo = models.CharField(max_length=20, primary_key=True)
    nombre = models.CharField(max_length=100)
    nombre_archivo = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Ciudades"

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"
