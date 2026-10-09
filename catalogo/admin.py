from django.contrib import admin
from django.utils.html import format_html

from .models import Material


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = (
        "codigo", "descripcion", "categoria", "stock_actual",
        "stock_reservado", "disponible_col", "punto_reabastecimiento",
        "alerta_col", "activo",
    )
    list_filter = ("categoria", "activo")
    search_fields = ("codigo", "descripcion")
    readonly_fields = ("stock_actual", "stock_reservado")

    @admin.display(description="Disponible")
    def disponible_col(self, obj):
        return obj.stock_disponible

    @admin.display(description="Alerta")
    def alerta_col(self, obj):
        if obj.stock_critico:
            return format_html('<b style="color:#b00020;">Stock bajo</b>')
        return "OK"
