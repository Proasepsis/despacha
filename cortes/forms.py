from django import forms

from integraciones_siigo.models import IngestionSiigo


class IngestionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return (
            f"{obj.window_start} → {obj.window_end} · "
            f"{obj.row_count} filas · {obj.extraction_id}"
        )


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
        queryset=IngestionSiigo.objects.order_by("-recibido_en"),
        required=False,
        label="Ingesta SIIGO",
        empty_label="Seleccione una ingesta…",
    )
    numero_corte = forms.ChoiceField(
        choices=[(1, "Corte 1"), (2, "Corte 2")],
        help_text="Sugerido según la hora; puede ajustarse.",
    )
    es_adicional = forms.BooleanField(required=False, label="Es adicional")

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
