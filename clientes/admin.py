from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nit", "nombre", "ciudad", "sucursal", "creado_en"]
    search_fields = ["nit", "nombre"]
    list_filter = ["ciudad"]
