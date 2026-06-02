from django.contrib import admin
from .models import ParametroSalida, ReglaClasificacion, NotificacionDestinatarios


def _es_admin(user):
    return user.groups.filter(name="admin").exists()


@admin.register(ParametroSalida)
class ParametroSalidaAdmin(admin.ModelAdmin):
    list_display = ["clave", "valor", "descripcion"]
    search_fields = ["clave", "descripcion"]

    def has_delete_permission(self, request, obj=None):
        return _es_admin(request.user)


@admin.register(ReglaClasificacion)
class ReglaClasificacionAdmin(admin.ModelAdmin):
    list_display = ["nombre", "campo_destino", "valor_por_defecto", "activa", "prioridad"]
    list_filter = ["activa", "campo_destino"]

    def has_delete_permission(self, request, obj=None):
        return _es_admin(request.user)


@admin.register(NotificacionDestinatarios)
class NotificacionDestinatariosAdmin(admin.ModelAdmin):
    list_display = ["evento", "correos", "activo"]
    list_filter = ["activo"]

    def has_delete_permission(self, request, obj=None):
        return _es_admin(request.user)
