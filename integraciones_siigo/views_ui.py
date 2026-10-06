from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View

from cortes.views import EsFacturacionOAdminMixin

from . import solicitudes
from .models import SolicitudExtraccion


class SolicitudForm(forms.Form):
    fecha_inicio = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    fecha_fin = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        data = super().clean()
        if "fecha_inicio" in data and "fecha_fin" in data:
            try:
                solicitudes.validar_rango(data["fecha_inicio"], data["fecha_fin"])
            except ValueError as e:
                raise forms.ValidationError(str(e))
        return data


class SolicitudesView(LoginRequiredMixin, EsFacturacionOAdminMixin, View):
    """Historial de solicitudes de extracción SIIGO y formulario para crear una."""

    raise_exception = True

    def _render(self, request, form):
        solicitudes.vencer_tomadas()
        lista = SolicitudExtraccion.objects.select_related("creada_por")[:100]
        return render(request, "siigo/solicitudes.html", {"form": form, "solicitudes": lista})

    def get(self, request):
        return self._render(request, SolicitudForm())

    def post(self, request):
        form = SolicitudForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)
        solicitudes.crear_solicitud(form.cleaned_data["fecha_inicio"], form.cleaned_data["fecha_fin"], request.user)
        return redirect("siigo-solicitudes")
