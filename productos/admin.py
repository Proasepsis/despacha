from django.contrib import admin
from .models import Producto, Ciudad


def _es_admin(user):
    return user.groups.filter(name="admin").exists()


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ["producto", "referencia", "descripcion", "unidad_empaque", "activo", "revisado"]
    search_fields = ["producto", "referencia"]
    list_filter = ["activo", "revisado"]
    list_per_page = 50
    show_full_result_count = False

    def has_delete_permission(self, request, obj=None):
        return _es_admin(request.user)


@admin.register(Ciudad)
class CiudadAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre", "nombre_archivo", "activo"]
    search_fields = ["codigo", "nombre"]
    list_filter = ["activo"]

    def has_delete_permission(self, request, obj=None):
        return _es_admin(request.user)
