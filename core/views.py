import csv
import os
from io import StringIO

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View
from django.views.generic import ListView

from cortes.models import Auditoria


class EsAdminMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.groups.filter(name="admin").exists()


class PanelConfigView(LoginRequiredMixin, EsAdminMixin, View):
    template_name = "core/config.html"

    def get(self, request):
        drive_ok = bool(
            os.environ.get("DRIVE_SERVICE_ACCOUNT_JSON", "")
            and os.path.exists(os.environ.get("DRIVE_SERVICE_ACCOUNT_JSON", ""))
        )
        drive_root = os.environ.get("DRIVE_ROOT_FOLDER_ID", "")
        smtp_ok = bool(os.environ.get("EMAIL_HOST_USER", ""))
        debug = os.environ.get("DEBUG", "False") == "True"
        env_name = os.environ.get("ENVIRONMENT", "producción")

        return render(request, self.template_name, {
            "drive_ok": drive_ok,
            "drive_root": drive_root,
            "smtp_ok": smtp_ok,
            "debug": debug,
            "env_name": env_name,
        })


class AuditoriaListView(LoginRequiredMixin, EsAdminMixin, ListView):
    model = Auditoria
    template_name = "core/auditoria.html"
    context_object_name = "registros"
    paginate_by = 50

    def get_queryset(self):
        qs = Auditoria.objects.select_related("usuario").all()
        tipo = self.request.GET.get("tipo_evento")
        if tipo:
            qs = qs.filter(tipo_evento=tipo)
        obj_tipo = self.request.GET.get("objeto_tipo")
        if obj_tipo:
            qs = qs.filter(objeto_tipo=obj_tipo)
        usuario_id = self.request.GET.get("usuario")
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        fecha_desde = self.request.GET.get("fecha_desde")
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        fecha_hasta = self.request.GET.get("fecha_hasta")
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from cortes.models import Auditoria as A
        ctx["tipos_evento"] = A.EVENTO_CHOICES
        ctx["query_string"] = self.request.GET.urlencode()
        return ctx

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get("export") == "csv":
            return self._export_csv(context["registros"])
        return super().render_to_response(context, **response_kwargs)

    def _export_csv(self, queryset):
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["fecha", "usuario", "objeto_tipo", "objeto_id",
                          "campo", "valor_anterior", "valor_nuevo", "tipo_evento"])
        for r in queryset.select_related("usuario"):
            writer.writerow([
                r.fecha.isoformat(),
                r.usuario.username if r.usuario else "",
                r.objeto_tipo, r.objeto_id,
                r.campo, r.valor_anterior, r.valor_nuevo, r.tipo_evento,
            ])
        response = HttpResponse(buf.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="auditoria.csv"'
        return response
