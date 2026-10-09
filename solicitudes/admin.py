"""
Admin de solicitudes. Como todavía no hay interfaz propia (quedó para el
próximo incremento), acá se exponen acciones del admin que llaman
directamente a solicitudes/services.py, para poder probar el circuito
completo (crear -> aprobar -> preparar -> entregar) sin escribir código.

Nota: las acciones del admin corren sobre la selección de una grilla, así
que para flujos que necesitan un dato adicional (ej. legajo de quien
retira) se dejaron como acciones simples que usan valores por defecto --
están pensadas para probar la lógica, no para el uso diario del almacén.
"""
from django.contrib import admin, messages

from . import services
from .models import ItemSolicitud, Solicitud


class ItemSolicitudInline(admin.TabularInline):
    model = ItemSolicitud
    extra = 1
    fk_name = "solicitud"
    autocomplete_fields = ("material", "maquina", "item_sustituto_de")
    readonly_fields = ("estado_item", "cantidad_reservada", "cantidad_entregada", "cantidad_devuelta")


@admin.register(ItemSolicitud)
class ItemSolicitudAdmin(admin.ModelAdmin):
    """
    Registrado también como pantalla propia (además de inline en Solicitud)
    para que otros admins puedan referenciarlo con autocomplete_fields
    (ej. inventario.Movimiento, presupuesto.GastoEquipo) y para poder
    buscar/filtrar ítems sueltos -- por ejemplo, todos los Faltantes
    pendientes de resolución.
    """

    list_display = ("id", "solicitud", "material", "cantidad_solicitada", "motivo", "estado_item")
    list_filter = ("estado_item", "motivo")
    search_fields = ("id", "material__codigo", "material__descripcion", "solicitud__id")
    autocomplete_fields = ("solicitud", "material", "maquina", "item_sustituto_de")


def _ejecutar_por_fila(request, queryset, accion, **kwargs):
    ok, error = 0, 0
    for obj in queryset:
        try:
            accion(obj, request.user, **kwargs)
            ok += 1
        except Exception as exc:  # ValidationError / PermissionDenied, etc.
            error += 1
            messages.error(request, f"{obj}: {exc}")
    if ok:
        messages.success(request, f"{ok} solicitud(es) procesada(s) correctamente.")
    if error:
        messages.warning(request, f"{error} solicitud(es) no se pudieron procesar (ver detalle arriba).")


@admin.register(Solicitud)
class SolicitudAdmin(admin.ModelAdmin):
    list_display = (
        "id", "equipo", "solicitante", "estado", "fecha_creacion",
        "aprobado_por", "entregado_por",
    )
    list_filter = ("estado", "equipo__area", "equipo")
    search_fields = ("id", "solicitante__username", "equipo__nombre", "legajo_retira")
    autocomplete_fields = ("solicitante", "equipo", "aprobado_por", "preparado_por", "entregado_por", "solicitud_origen")
    readonly_fields = (
        "fecha_creacion", "fecha_aprobacion", "fecha_entrega",
        "aprobado_por", "preparado_por", "entregado_por",
    )
    inlines = [ItemSolicitudInline]
    actions = [
        "accion_aprobar", "accion_rechazar", "accion_tomar_en_preparacion",
        "accion_marcar_lista", "accion_entregar_mostrador", "accion_cancelar",
    ]

    @admin.action(description="Aprobar solicitudes seleccionadas")
    def accion_aprobar(self, request, queryset):
        _ejecutar_por_fila(request, queryset, services.aprobar_solicitud)

    @admin.action(description="Rechazar solicitudes seleccionadas")
    def accion_rechazar(self, request, queryset):
        _ejecutar_por_fila(request, queryset, services.rechazar_solicitud)

    @admin.action(description="Tomar en preparación (operario de almacén)")
    def accion_tomar_en_preparacion(self, request, queryset):
        _ejecutar_por_fila(request, queryset, services.tomar_en_preparacion)

    @admin.action(description="Marcar lista para retirar")
    def accion_marcar_lista(self, request, queryset):
        _ejecutar_por_fila(request, queryset, services.marcar_lista_para_retirar)

    @admin.action(description="Confirmar entrega en mostrador (usa legajo del solicitante)")
    def accion_entregar_mostrador(self, request, queryset):
        for obj in queryset:
            legajo = getattr(getattr(obj.solicitante, "perfil", None), "legajo", "")
            nombre = obj.solicitante.get_full_name() or obj.solicitante.username
            try:
                services.confirmar_entrega(obj, request.user, legajo_retira=legajo, nombre_retira=nombre)
            except Exception as exc:
                messages.error(request, f"{obj}: {exc}")

    @admin.action(description="Cancelar solicitudes seleccionadas")
    def accion_cancelar(self, request, queryset):
        _ejecutar_por_fila(request, queryset, services.cancelar_solicitud)
