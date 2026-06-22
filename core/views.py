import csv
import os
import shutil
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


class EsAdminOConsultarMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        return self.request.user.groups.filter(name__in=["admin", "consultar"]).exists()


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

        recursos = _recursos_servidor()

        return render(request, self.template_name, {
            "drive_ok": drive_ok,
            "recursos": recursos,
            "drive_root": drive_root,
            "smtp_ok": smtp_ok,
            "debug": debug,
            "env_name": env_name,
        })


def _recursos_servidor():
    disco = shutil.disk_usage("/")
    ram = {"total_gb": 0, "disponible_gb": 0, "usado_pct": 0}
    try:
        with open("/proc/meminfo") as f:
            mem = {k.strip(): int(v.split()[0]) for k, v in (l.split(":") for l in f)}
        total_kb = mem["MemTotal"]
        disponible_kb = mem["MemAvailable"]
        ram = {
            "total_gb": round(total_kb / 1_048_576, 1),
            "disponible_gb": round(disponible_kb / 1_048_576, 1),
            "usado_pct": round((total_kb - disponible_kb) / total_kb * 100),
        }
    except Exception:
        pass
    load1, load5, _ = os.getloadavg()
    return {
        "disco_total_gb": round(disco.total / 1_073_741_824, 1),
        "disco_usado_gb": round(disco.used / 1_073_741_824, 1),
        "disco_libre_gb": round(disco.free / 1_073_741_824, 1),
        "disco_usado_pct": round(disco.used / disco.total * 100),
        "ram": ram,
        "load1": round(load1, 2),
        "load5": round(load5, 2),
    }


class AuditoriaListView(LoginRequiredMixin, EsAdminOConsultarMixin, ListView):
    model = Auditoria
    template_name = "core/auditoria.html"
    context_object_name = "registros"
    paginate_by = 50

    def get_queryset(self):
        from django.db.models import Q
        from cortes.models import Documento

        qs = Auditoria.objects.select_related("usuario").all()
        q = self.request.GET.get("q", "").strip()
        if q:
            doc_ids = list(
                Documento.objects.filter(factura__icontains=q).values_list("pk", flat=True)
            )
            qs = qs.filter(
                Q(valor_anterior__icontains=q)
                | Q(valor_nuevo__icontains=q)
                | Q(objeto_tipo="Documento", objeto_id__in=[str(pk) for pk in doc_ids])
            )
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
        from cortes.models import Auditoria as A, Documento
        ctx["tipos_evento"] = A.EVENTO_CHOICES
        ctx["query_string"] = self.request.GET.urlencode()

        page_records = ctx["registros"]
        doc_ids = [r.objeto_id for r in page_records if r.objeto_tipo == "Documento"]
        facturas_map = {}
        if doc_ids:
            facturas_map = {
                str(pk): factura
                for pk, factura in Documento.objects.filter(pk__in=doc_ids).values_list("pk", "factura")
            }
        for r in page_records:
            r.display_id = facturas_map.get(r.objeto_id, r.objeto_id) if r.objeto_tipo == "Documento" else r.objeto_id
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
