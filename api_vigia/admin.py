from django.contrib import admin

from .models import CredencialVigia


@admin.register(CredencialVigia)
class CredencialVigiaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "identificador", "activo", "ultimo_uso_en", "ultima_ip")
    list_filter = ("activo",)
    search_fields = ("nombre", "identificador")
    readonly_fields = (
        "identificador",
        "token_sha256",
        "creado_en",
        "ultimo_uso_en",
        "ultima_ip",
    )
