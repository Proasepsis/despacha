import json
import logging

from django.contrib.auth import logout as auth_logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView

from datetime import timedelta

from django.db.models import Count

from cortes.models import Corte, Documento, Linea, PresenciaCorte
from cortes.forms import CargarCorteForm
from cortes.servicios.corte_por_hora import sugerir_corte
from cortes.servicios.cargar import (
    cargar_archivo,
    ErrorDuplicado,
    ErrorValidacionAdaptador,
    ErrorCombinacionFechaCorte,
    ErrorSugerirAdicional,
)
from cortes.servicios.bloqueo import liberar_bloqueo
from cortes.servicios.split import partir_documento, deshacer_split
from cortes.servicios.auditoria import registrar_auditoria
from cortes.servicios.generar import generar_y_entregar

logger = logging.getLogger(__name__)


class EsFacturacionOAdminMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.groups.filter(name__in=["facturacion", "admin"]).exists()


class EsAlmacenamientoOAdminMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.groups.filter(name__in=["almacenamiento", "admin"]).exists()


class ListaCortesView(LoginRequiredMixin, ListView):
    model = Corte
    template_name = "cortes/lista.html"
    context_object_name = "cortes"
    paginate_by = 20

    def get_queryset(self):
        hace_30_dias = timezone.localdate() - timedelta(days=30)
        return super().get_queryset().filter(
            fecha__gte=hace_30_dias,
        ).annotate(
            documentos_count=Count("documentos"),
        )

    def get_context_data(self, **kwargs):
        from itertools import groupby
        ctx = super().get_context_data(**kwargs)
        dias = []
        for fecha, fecha_iter in groupby(ctx["cortes"], key=lambda c: c.fecha):
            grupos = []
            for numero, corte_iter in groupby(list(fecha_iter), key=lambda c: c.numero_corte):
                grupos.append(list(corte_iter))
            dias.append({"fecha": fecha, "grupos": grupos})
        ctx["dias"] = dias
        return ctx


class CargarCorteView(LoginRequiredMixin, EsFacturacionOAdminMixin, View):
    template_name = "cortes/cargar.html"

    def get(self, request):
        form = CargarCorteForm(initial={"numero_corte": str(sugerir_corte())})
        return render(request, self.template_name, {
            "form": form,
            "corte_sugerido": sugerir_corte(),
        })

    def post(self, request):
        form = CargarCorteForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {
                "form": form,
                "corte_sugerido": sugerir_corte(),
            })

        try:
            corte, resultado = cargar_archivo(
                archivo=form.cleaned_data["archivo"],
                usuario=request.user,
                formato_origen=form.cleaned_data["formato_origen"],
                numero_corte=int(form.cleaned_data["numero_corte"]),
                es_adicional=form.cleaned_data.get("es_adicional", False),
            )
        except ErrorDuplicado as e:
            form.add_error(None, str(e))
            return render(request, self.template_name, {
                "form": form,
                "corte_sugerido": sugerir_corte(),
            })
        except ErrorValidacionAdaptador as e:
            form.add_error("archivo", str(e))
            return render(request, self.template_name, {
                "form": form,
                "corte_sugerido": sugerir_corte(),
            })
        except ErrorSugerirAdicional as e:
            return render(request, self.template_name, {
                "form": form,
                "corte_sugerido": sugerir_corte(),
                "sugerir_adicional": True,
                "msg_sugerencia": str(e),
            })
        except ErrorCombinacionFechaCorte as e:
            form.add_error(None, str(e))
            return render(request, self.template_name, {
                "form": form,
                "corte_sugerido": sugerir_corte(),
            })

        return redirect("lista_cortes")


class DetalleCorteView(LoginRequiredMixin, DetailView):
    model = Corte
    template_name = "cortes/detalle.html"
    context_object_name = "corte"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        corte = self.object
        user = self.request.user

        grupos = set(user.groups.values_list("name", flat=True))
        es_editor = bool(grupos & {"almacenamiento", "admin"})

        documentos = corte.documentos.prefetch_related("lineas").all()
        docs_data = []
        for doc in documentos:
            lineas_data = []
            for linea in doc.lineas.all():
                lineas_data.append({
                    "id": linea.id,
                    "referencia": linea.referencia_snapshot,
                    "descripcion": linea.descripcion_snapshot,
                    "lote": linea.lote,
                    "cantidad_unidades": str(linea.cantidad_unidades),
                    "sin_maestro": linea.sin_maestro,
                    "inactivo": linea.inactivo,
                })
            docs_data.append({
                "id": doc.id,
                "factura": doc.factura,
                "nit": doc.nit,
                "clasificador1": doc.clasificador1,
                "observaciones": doc.observaciones,
                "subsanar_novedad": doc.subsanar_novedad,
                "factura_sufijo": doc.factura_sufijo,
                "lineas": lineas_data,
            })

        sin_maestro_count = sum(
            1 for d in docs_data for l in d["lineas"] if l["sin_maestro"]
        )

        ctx.update({
            "documentos_data": docs_data,
            "documentos_count": len(docs_data),
            "lineas_count": sum(len(d["lineas"]) for d in docs_data),
            "sin_maestro_count": sin_maestro_count,
            "es_editor": es_editor,
            "clasificador1_opciones": ["EMBALAR", "NO EMBALAR", "PREGUNTAR"],
            "prioridad_opciones": ["PRIORIDAD", "NO PRIORIDAD"],
        })
        return ctx


class EditarCorteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        corte = get_object_or_404(Corte, pk=pk)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest("JSON inválido")

        tipo = body.get("tipo")
        obj_id = body.get("id")
        campo = body.get("campo")
        valor = body.get("valor")

        if not tipo or not obj_id or not campo:
            return HttpResponseBadRequest("Faltan campos requeridos")

        grupos = set(request.user.groups.values_list("name", flat=True))
        if not bool(grupos & {"almacenamiento", "admin"}):
            return HttpResponseForbidden("Sin permisos para editar")

        try:
            with transaction.atomic():
                if tipo == "documento":
                    doc = get_object_or_404(Documento, pk=obj_id, corte=corte)
                    valor_anterior = getattr(doc, campo)
                    if campo not in ("clasificador1", "observaciones", "subsanar_novedad", "factura_sufijo"):
                        return HttpResponseBadRequest(f"Campo no editable: {campo}")
                    if campo == "factura_sufijo" and not doc.subsanar_novedad:
                        return HttpResponseBadRequest("No se puede editar sufijo sin novedad activa")
                    if campo == "subsanar_novedad":
                        valor = valor == "true"
                    if campo == "factura_sufijo" and isinstance(valor, str):
                        valor = valor.upper()
                    setattr(doc, campo, valor)
                    if campo == "subsanar_novedad" and not valor:
                        doc.factura_sufijo = ""
                        doc.save(update_fields=[campo, "factura_sufijo"])
                    else:
                        doc.save(update_fields=[campo])
                    registrar_auditoria(
                        usuario=request.user,
                        objeto_tipo="Documento",
                        objeto_id=str(doc.pk),
                        campo=campo,
                        valor_anterior=str(valor_anterior),
                        valor_nuevo=str(valor),
                        tipo_evento="edicion",
                    )

                elif tipo == "linea":
                    linea = get_object_or_404(Linea, pk=obj_id, documento__corte=corte)
                    if campo != "cantidad_unidades":
                        return HttpResponseBadRequest(f"Campo no editable: {campo}")

                    try:
                        nuevo_valor = str(valor)
                        from decimal import Decimal, InvalidOperation
                        dec = Decimal(nuevo_valor)
                        if dec <= 0:
                            return HttpResponseBadRequest("La cantidad debe ser positiva")
                    except (InvalidOperation, ValueError):
                        return HttpResponseBadRequest("Cantidad inválida")

                    valor_anterior = linea.cantidad_unidades
                    linea.cantidad_unidades = dec
                    linea.save(update_fields=["cantidad_unidades"])

                    registrar_auditoria(
                        usuario=request.user,
                        objeto_tipo="Linea",
                        objeto_id=str(linea.pk),
                        campo="cantidad_unidades",
                        valor_anterior=str(valor_anterior),
                        valor_nuevo=str(dec),
                        tipo_evento="edicion",
                    )

                else:
                    return HttpResponseBadRequest(f"Tipo desconocido: {tipo}")

        except Exception:
            return JsonResponse({"ok": False, "error": "Error al guardar"}, status=500)

        return JsonResponse({
            "ok": True,
            "ultima_edicion": timezone.now().strftime("%H:%M"),
        })


class SplitDocumentoView(LoginRequiredMixin, View):
    def post(self, request, pk):
        corte = get_object_or_404(Corte, pk=pk)

        grupos = set(request.user.groups.values_list("name", flat=True))
        if not bool(grupos & {"almacenamiento", "admin"}):
            return HttpResponseForbidden("Sin permisos para editar")

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest("JSON inválido")

        documento_id = body.get("documento_id")
        lineas_ids = body.get("lineas_ids", [])

        if not documento_id or not lineas_ids:
            return HttpResponseBadRequest("Faltan documento_id o lineas_ids")

        doc = get_object_or_404(Documento, pk=documento_id, corte=corte)

        try:
            nuevo_doc = partir_documento(doc, lineas_ids, request.user)
        except ValueError as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

        return JsonResponse({
            "ok": True,
            "nuevo_documento_id": nuevo_doc.pk,
            "nueva_factura": nuevo_doc.factura,
        })


class DeshacerSplitView(LoginRequiredMixin, View):
    def post(self, request, pk):
        corte = get_object_or_404(Corte, pk=pk)

        grupos = set(request.user.groups.values_list("name", flat=True))
        if not bool(grupos & {"almacenamiento", "admin"}):
            return HttpResponseForbidden("Sin permisos para editar")

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest("JSON inválido")

        documento_id = body.get("documento_id")
        if not documento_id:
            return HttpResponseBadRequest("Falta documento_id")

        doc = get_object_or_404(Documento, pk=documento_id, corte=corte)

        try:
            deshacer_split(doc, request.user)
        except ValueError as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

        return JsonResponse({"ok": True})


class ForzarLiberacionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not request.user.groups.filter(name="admin").exists():
            return HttpResponseForbidden("Solo admin puede forzar liberación")

        corte = get_object_or_404(Corte, pk=pk)
        liberar_bloqueo(corte, request.user, forzado_por_admin=True)
        return JsonResponse({"ok": True})


class GenerarCorteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        corte = get_object_or_404(Corte, pk=pk)

        grupos = set(request.user.groups.values_list("name", flat=True))
        if not bool(grupos & {"almacenamiento", "admin"}):
            return HttpResponseForbidden("Sin permisos para generar")

        destinos = request.POST.getlist("destinos")
        motivo = request.POST.get("motivo", "")

        try:
            resultado = generar_y_entregar(
                corte=corte,
                destinos=destinos,
                usuario=request.user,
                motivo=motivo,
            )
        except ValueError as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

        if not resultado["success"]:
            for msg in resultado.get("errores", []):
                logger.error("Corte %s — fallo destino: %s", corte.pk, msg)
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Algunos destinos fallaron",
                    "resultados": resultado["resultados"],
                },
                status=500,
            )

        response = JsonResponse({
            "ok": True,
            "version": resultado["version"],
            "nombre_archivo": resultado["nombre_archivo"],
            "resultados": resultado["resultados"],
        })

        if "descarga" in destinos and resultado["resultados"]["descarga"]["ok"]:
            response = __class__._respuesta_descarga(resultado, response)

        return response

    @staticmethod
    def _respuesta_descarga(resultado, fallback_response):
        try:
            from django.http import HttpResponse
            response = HttpResponse(
                resultado["archivo_bytes"],
                content_type="application/vnd.ms-excel",
            )
            filename = resultado["nombre_archivo"]
            response["Content-Disposition"] = (
                f'attachment; filename="{filename}"'
            )
            return response
        except Exception:
            return fallback_response


class PresenciaPingView(LoginRequiredMixin, View):
    def post(self, request, pk):
        corte = get_object_or_404(Corte, pk=pk)
        PresenciaCorte.objects.update_or_create(
            user=request.user,
            corte=corte,
            defaults={"visto_en": timezone.now()},
        )
        return JsonResponse({"ok": True})

    def get(self, request, pk):
        corte = get_object_or_404(Corte, pk=pk)
        limite = timezone.now() - timedelta(seconds=25)
        PresenciaCorte.objects.filter(corte=corte, visto_en__lt=limite).delete()
        activos = PresenciaCorte.objects.filter(corte=corte).select_related("user")
        usuarios = []
        for p in activos:
            first = p.user.first_name[:1] if p.user.first_name else ""
            last = p.user.last_name[:1] if p.user.last_name else ""
            iniciales = (first + last).upper() or p.user.username[:2].upper()
            usuarios.append({
                "username": p.user.username,
                "iniciales": iniciales,
                "soy_yo": p.user_id == request.user.pk,
            })
        return JsonResponse({"usuarios": usuarios})


class LogoutView(View):
    def post(self, request):
        auth_logout(request)
        return redirect("admin:login")
