from django import forms
from django.utils import timezone

from core.adaptadores.api_siigo.convertir import filas_a_documentos_internos
from cortes.servicios.cargar_ingesta import NUMERO_POR_CUT
from integraciones_siigo.models import IngestionSiigo


class IngestionChoiceField(forms.ModelChoiceField):
    documentos_por_ingesta: dict[int, int] = {}

    def label_from_instance(self, obj):
        partes = [f"{timezone.localtime(obj.generated_at):%d/%m/%Y %H:%M}"]
        nombre = (obj.payload.get("cut") or {}).get("nombre")
        if nombre in NUMERO_POR_CUT:
            partes.append(f"Corte {NUMERO_POR_CUT[nombre]}")
        elif nombre == "recuperacion":
            # El extractor manda una recuperación por día de documentos, todas a la misma hora
            partes.append(f"Recuperación del {obj.window_start:%d/%m}")
        elif nombre == "extra":
            partes.append("Extra")
        n = self.documentos_por_ingesta.get(obj.pk, 0)
        partes.append(f"{n} documento{'' if n == 1 else 's'}")
        return " · ".join(partes)


class CargarCorteForm(forms.Form):
    archivo = forms.FileField(
        label="Archivo (.xlsx)",
        help_text="Tamaño máximo: 10 MB",
        required=False,
    )
    formato_origen = forms.ChoiceField(
        choices=[("PLANTILLA", "PLANTILLA"), ("API_SIIGO", "SIIGO API")],
        initial="PLANTILLA",
    )
    ingestion = IngestionChoiceField(
        queryset=IngestionSiigo.objects.none(),
        required=False,
        label="Ingesta SIIGO",
        empty_label="Seleccione una ingesta…",
    )
    numero_corte = forms.ChoiceField(
        choices=[(1, "Corte 1"), (2, "Corte 2")],
        help_text="Sugerido según la hora; puede ajustarse.",
    )
    es_adicional = forms.BooleanField(required=False, label="Es adicional")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo ingestas con documentos que Despacha puede procesar, con el mismo filtro de cargar_ingesta.
        # ponytail: convierte todas las ingestas en cada carga del formulario; si la lista crece
        # y se vuelve lenta, guardar el conteo al recibir la ingesta.
        documentos = {
            ingesta.pk: len(filas_a_documentos_internos(ingesta.payload.get("rows", [])))
            for ingesta in IngestionSiigo.objects.filter(row_count__gt=0).only("pk", "payload")
        }
        campo = self.fields["ingestion"]
        campo.documentos_por_ingesta = documentos
        campo.queryset = (
            IngestionSiigo.objects.filter(pk__in=[pk for pk, n in documentos.items() if n])
            .order_by("-generated_at")
        )

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if archivo is None:
            return archivo
        if archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError("El archivo supera 10 MB.")
        nombre = archivo.name.lower()
        if not (nombre.endswith(".xlsx") or nombre.endswith(".xls")):
            raise forms.ValidationError("Formato no soportado. Use .xlsx o .xls.")
        return archivo

    def clean(self):
        cleaned = super().clean()
        formato = cleaned.get("formato_origen")
        if formato == "API_SIIGO":
            if not cleaned.get("ingestion"):
                self.add_error("ingestion", "Seleccione una ingesta SIIGO.")
        elif formato == "PLANTILLA":
            if not cleaned.get("archivo"):
                self.add_error("archivo", "Seleccione un archivo .xlsx.")
        return cleaned
