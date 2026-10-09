from django.contrib import admin

from .models import GastoEquipo, PresupuestoMensual


@admin.register(PresupuestoMensual)
class PresupuestoMensualAdmin(admin.ModelAdmin):
    list_display = ("equipo", "mes", "anio", "monto_asignado", "gasto_neto_col", "saldo_col", "cargado_por")
    list_filter = ("anio", "mes", "equipo__area")
    autocomplete_fields = ("equipo", "cargado_por")
    readonly_fields = ("fecha_carga",)

    @admin.display(description="Gasto del mes")
    def gasto_neto_col(self, obj):
        return obj.gasto_neto

    @admin.display(description="Saldo")
    def saldo_col(self, obj):
        return obj.saldo

    def save_model(self, request, obj, form, change):
        if not change:
            obj.cargado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(GastoEquipo)
class GastoEquipoAdmin(admin.ModelAdmin):
    """Solo lectura: se genera automáticamente desde el flujo de solicitudes."""

    list_display = ("fecha", "equipo", "mes", "anio", "monto", "motivo", "item_solicitud")
    list_filter = ("anio", "mes", "equipo__area")
    search_fields = ("equipo__nombre",)
    readonly_fields = [f.name for f in GastoEquipo._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
