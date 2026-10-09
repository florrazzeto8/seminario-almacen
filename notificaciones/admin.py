from django.contrib import admin

from .models import AvisoCompras, Notificacion


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ("fecha", "destinatario", "tipo", "mensaje", "leida", "solicitud")
    list_filter = ("tipo", "leida")
    search_fields = ("destinatario__username", "mensaje")
    autocomplete_fields = ("destinatario", "solicitud")


@admin.register(AvisoCompras)
class AvisoComprasAdmin(admin.ModelAdmin):
    list_display = ("fecha", "material", "motivo", "enviado", "detalle")
    list_filter = ("motivo", "enviado")
    search_fields = ("material__codigo", "material__descripcion")
    autocomplete_fields = ("material",)
