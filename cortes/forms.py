from django import forms


class CargarCorteForm(forms.Form):
    archivo = forms.FileField(
        label="Archivo (.xlsx)",
        help_text="Tamaño máximo: 10 MB",
    )
    formato_origen = forms.ChoiceField(
        choices=[("PLANTILLA", "PLANTILLA")],
        initial="PLANTILLA",
    )
    numero_corte = forms.ChoiceField(
        choices=[(1, "Corte 1"), (2, "Corte 2")],
        help_text="Sugerido según la hora; puede ajustarse.",
    )
    adicional_letra = forms.CharField(
        required=False,
        max_length=1,
        label="Letra adicional",
    )

    def clean_adicional_letra(self):
        val = self.cleaned_data.get("adicional_letra", "").strip().upper()
        if val and not val.isalpha():
            raise forms.ValidationError("Solo se permite una letra (A–Z).")
        return val

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError("El archivo supera 10 MB.")
        nombre = archivo.name.lower()
        if not (nombre.endswith(".xlsx") or nombre.endswith(".xls")):
            raise forms.ValidationError("Formato no soportado. Use .xlsx o .xls.")
        return archivo
