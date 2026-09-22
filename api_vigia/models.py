from django.db import models


class CredencialVigia(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    identificador = models.CharField(max_length=16, unique=True, editable=False)
    token_sha256 = models.CharField(max_length=64, editable=False)
    ips_permitidas = models.JSONField(default=list, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    ultimo_uso_en = models.DateTimeField(null=True, blank=True)
    ultima_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "Credencial de API Vigia"
        verbose_name_plural = "Credenciales de API Vigia"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
