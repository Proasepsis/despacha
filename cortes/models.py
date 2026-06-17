from django.conf import settings
from django.db import models


class Corte(models.Model):
    ESTADO_CHOICES = [
        ("cargado", "Cargado"),
        ("en_revision", "En revisión"),
        ("generado", "Generado"),
        ("con_error", "Con error"),
    ]

    CORTE_CHOICES = [
        (1, "Corte 1"),
        (2, "Corte 2"),
    ]

    archivo = models.CharField(max_length=255)
    formato_origen = models.CharField(max_length=20, default="PLANTILLA")
    hash_sha256 = models.CharField(max_length=64, db_index=True)
    usuario_carga = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateField(db_index=True)
    numero_corte = models.PositiveSmallIntegerField(choices=CORTE_CHOICES)
    adicional_letra = models.CharField(max_length=1, blank=True, default="")
    estado = models.CharField(
        max_length=20, choices=ESTADO_CHOICES, default="cargado", db_index=True
    )
    version_actual = models.PositiveSmallIntegerField(default=0)
    bloqueado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cortes_bloqueados",
    )
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha", "numero_corte", "adicional_letra"]
        constraints = [
            models.UniqueConstraint(
                fields=["fecha", "numero_corte", "adicional_letra"],
                name="uq_corte_fecha_numero_letra",
            )
        ]

    @property
    def display_corte(self):
        base = f"Corte {self.numero_corte}"
        if self.adicional_letra:
            base += self.adicional_letra
        return base

    def __str__(self):
        return f"{self.display_corte} {self.fecha:%d/%m/%Y} (v{self.version_actual})"


class CorteVersion(models.Model):
    corte = models.ForeignKey(Corte, on_delete=models.CASCADE, related_name="versiones")
    numero = models.PositiveSmallIntegerField()
    drive_url = models.URLField(blank=True)
    archivo_hash = models.CharField(max_length=64)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_generacion = models.DateTimeField(auto_now_add=True)
    motivo = models.TextField(blank=True)

    class Meta:
        ordering = ["corte", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["corte", "numero"], name="uq_corte_version")
        ]

    def __str__(self):
        return f"{self.corte} — versión {self.numero}"


class Documento(models.Model):
    corte = models.ForeignKey(Corte, on_delete=models.CASCADE, related_name="documentos")
    factura = models.CharField(max_length=30)
    nit = models.CharField(max_length=20, blank=True)
    tipo_comprobante = models.CharField(max_length=1, blank=True, default="")
    ciudad = models.ForeignKey(
        "productos.Ciudad",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    clasificador1 = models.CharField(max_length=20, default="EMBALAR")
    observaciones = models.CharField(max_length=20, default="PRIORIDAD")
    subsanar_novedad = models.BooleanField(default=False)
    factura_sufijo   = models.CharField(max_length=10, blank=True, default="")
    creado_por_split_de = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documentos_hijos",
    )

    class Meta:
        ordering = ["factura"]

    def __str__(self):
        return self.factura


class Linea(models.Model):
    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name="lineas")
    referencia = models.CharField(max_length=50)
    lote = models.CharField(max_length=50)
    cantidad_origen = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_unidades = models.PositiveIntegerField()
    sin_maestro = models.BooleanField(default=False, db_index=True)
    inactivo = models.BooleanField(default=False)
    referencia_snapshot = models.CharField(max_length=50)
    descripcion_snapshot = models.CharField(max_length=200)
    unidad_empaque_snapshot = models.PositiveIntegerField()
    movida_desde = models.ForeignKey(
        Documento,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lineas_movidas_a_otros",
    )

    class Meta:
        ordering = ["id"]


class Auditoria(models.Model):
    EVENTO_CHOICES = [
        ("edicion", "Edición"),
        ("regeneracion", "Regeneración"),
        ("split", "Split de documento"),
        ("deshacer_split", "Deshacer split"),
        ("forzar_liberacion", "Forzar liberación"),
        ("creacion", "Creación"),
        ("inactivacion", "Inactivación"),
        ("login_fallido", "Login fallido"),
        ("notificacion_fallida", "Notificación fallida"),
    ]

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    objeto_tipo = models.CharField(max_length=50)
    objeto_id = models.CharField(max_length=50)
    campo = models.CharField(max_length=50, blank=True)
    valor_anterior = models.TextField(blank=True)
    valor_nuevo = models.TextField(blank=True)
    tipo_evento = models.CharField(max_length=30, choices=EVENTO_CHOICES)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["objeto_tipo", "objeto_id"]),
        ]

    def __str__(self):
        return f"[{self.fecha:%Y-%m-%d %H:%M}] {self.usuario} — {self.tipo_evento} {self.objeto_tipo}#{self.objeto_id}"


class PresenciaCorte(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="presencias_corte",
    )
    corte = models.ForeignKey(
        Corte,
        on_delete=models.CASCADE,
        related_name="presencias",
    )
    visto_en = models.DateTimeField()

    class Meta:
        unique_together = [("user", "corte")]
