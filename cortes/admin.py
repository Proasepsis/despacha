from django.contrib import admin
from .models import Corte, CorteVersion, Documento, Linea, Auditoria


def _es_admin(user):
    return user.groups.filter(name="admin").exists()


@admin.register(Corte)
class CorteAdmin(admin.ModelAdmin):
    list_display = ["fecha", "numero_corte", "version_actual", "estado", "usuario_carga", "creado_en"]
    list_filter = ["estado", "fecha", "numero_corte"]
    readonly_fields = ["hash_sha256", "creado_en"]
    search_fields = ["archivo"]

    def has_delete_permission(self, request, obj=None):
        return _es_admin(request.user)


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ["factura", "corte", "nit", "clasificador1", "observaciones", "ciudad"]
    list_filter = ["corte"]
    search_fields = ["factura", "nit"]

    def has_add_permission(self, request):
        return _es_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return _es_admin(request.user)


@admin.register(Linea)
class LineaAdmin(admin.ModelAdmin):
    list_display = [
        "id", "documento", "referencia", "lote", "cantidad_origen",
        "cantidad_unidades", "sin_maestro", "inactivo",
    ]
    list_filter = ["sin_maestro", "inactivo"]
    search_fields = ["referencia", "lote"]

    def has_add_permission(self, request):
        return _es_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return _es_admin(request.user)


@admin.register(CorteVersion)
class CorteVersionAdmin(admin.ModelAdmin):
    list_display = ["corte", "numero", "fecha_generacion", "usuario"]
    readonly_fields = ["fecha_generacion"]

    def has_add_permission(self, request):
        return _es_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return _es_admin(request.user)


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ["fecha", "usuario", "objeto_tipo", "objeto_id", "campo", "tipo_evento"]
    list_filter = ["tipo_evento", "objeto_tipo", "fecha"]
    search_fields = ["objeto_id", "usuario__username"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
