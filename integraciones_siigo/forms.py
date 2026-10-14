from django import forms

from . import solicitudes


class SolicitudForm(forms.Form):
    fecha_inicio = forms.DateField(label="Desde", widget=forms.DateInput(attrs={"type": "date", "form": "solicitud-form"}))
    fecha_fin = forms.DateField(label="Hasta", widget=forms.DateInput(attrs={"type": "date", "form": "solicitud-form"}))

    def clean(self):
        data = super().clean()
        if "fecha_inicio" in data and "fecha_fin" in data:
            try:
                solicitudes.validar_rango(data["fecha_inicio"], data["fecha_fin"])
            except ValueError as e:
                raise forms.ValidationError(str(e))
        return data
