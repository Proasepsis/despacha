from django.db import models


class Cliente(models.Model):
    nit = models.CharField(max_length=20, primary_key=True)
    sucursal = models.CharField(max_length=20, blank=True)
    dv = models.CharField(max_length=5, blank=True)
    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=5, blank=True)
    direccion = models.CharField(max_length=200, blank=True)
    ciudad = models.CharField(max_length=100, blank=True)
    fax = models.CharField(max_length=20, blank=True)
    telefono_1 = models.CharField(max_length=20, blank=True)
    telefono_2 = models.CharField(max_length=20, blank=True)
    telefono_3 = models.CharField(max_length=20, blank=True)
    telefono_4 = models.CharField(max_length=20, blank=True)
    apartado = models.CharField(max_length=20, blank=True)
    clasificacion = models.CharField(max_length=50, blank=True)
    forma_pago = models.CharField(max_length=20, blank=True)
    dia = models.CharField(max_length=10, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def __str__(self):
        return f"{self.nit} - {self.nombre}"
