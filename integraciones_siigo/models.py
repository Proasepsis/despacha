import uuid

from django.conf import settings
from django.db import models


class IngestionSiigo(models.Model):
    ESTADO_RECIBIDO = "recibido"
    ESTADOS = [(ESTADO_RECIBIDO, "Recibido")]

    extraction_id = models.UUIDField(unique=True)
    schema_version = models.CharField(max_length=20)
    source = models.CharField(max_length=50)
    window_start = models.DateField()
    window_end = models.DateField()
    generated_at = models.DateTimeField()
    raw_sha256 = models.CharField(max_length=64)
    raw_size_bytes = models.PositiveBigIntegerField()
    content_sha256 = models.CharField(max_length=64)
    rows_sha256 = models.CharField(max_length=64, db_index=True)
    row_count = models.PositiveIntegerField()
    payload = models.JSONField()
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_RECIBIDO)
    recibido_en = models.DateTimeField(auto_now_add=True)
    solicitud = models.ForeignKey(
        "SolicitudExtraccion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ingestiones",
    )

    class Meta:
        ordering = ["-recibido_en"]
        verbose_name = "Ingestión SIIGO"
        verbose_name_plural = "Ingestiones SIIGO"

    def __str__(self):
        return f"{self.extraction_id} ({self.row_count} filas)"


class SolicitudExtraccion(models.Model):
    PENDIENTE, TOMADA, COMPLETADA, FALLIDA = "pendiente", "tomada", "completada", "fallida"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (TOMADA, "Tomada"),
        (COMPLETADA, "Completada"),
        (FALLIDA, "Fallida"),
    ]

    solicitud_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    creada_en = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=PENDIENTE, db_index=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    tomada_en = models.DateTimeField(null=True, blank=True)
    completada_en = models.DateTimeField(null=True, blank=True)
    extraction_id = models.UUIDField(null=True, blank=True)
    row_count = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-creada_en"]
        verbose_name = "Solicitud de extracción"
        verbose_name_plural = "Solicitudes de extracción"

    def __str__(self):
        return f"{self.solicitud_id} {self.fecha_inicio}..{self.fecha_fin} ({self.estado})"


class FilaSiigo(models.Model):
    """Foto vigente de SIIGO por fila, alimentada solo por solicitudes. Clave: documento + secuencia."""

    tipo_comprobante = models.CharField(max_length=5)
    codigo_comprobante = models.CharField(max_length=10)
    numero_documento = models.CharField(max_length=30)
    secuencia = models.CharField(max_length=20)
    fecha_documento = models.DateField(db_index=True)
    fila = models.JSONField()
    ingestion = models.ForeignKey(IngestionSiigo, on_delete=models.CASCADE, related_name="filas_siigo")
    no_presente_en_siigo = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_comprobante", "codigo_comprobante", "numero_documento", "secuencia"],
                name="fila_siigo_unica",
            )
        ]
