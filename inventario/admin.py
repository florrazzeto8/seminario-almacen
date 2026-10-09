from django.contrib import admin

from .models import Movimiento


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    """
    Los movimientos son inmutables: este admin es de solo lectura. Para
    generar movimientos se usan las funciones de inventario/services.py
    (ingreso, ajuste) o el flujo de solicitudes (salida, devolución),
    nunca editando un registro existente.
    """

    list_display = ("fecha", "tipo", "material", "cantidad", "usuario", "item_solicitud")
    list_filter = ("tipo", "fecha")
    search_fields = ("material__codigo", "material__descripcion", "observacion")
    autocomplete_fields = ("material", "usuario", "item_solicitud")
    readonly_fields = [f.name for f in Movimiento._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
