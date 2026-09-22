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

    class Meta:
        ordering = ["-recibido_en"]
        verbose_name = "Ingestión SIIGO"
        verbose_name_plural = "Ingestiones SIIGO"

    def __str__(self):
        return f"{self.extraction_id} ({self.row_count} filas)"
