"""
inventario: historial de movimientos de stock.

Los movimientos son INMUTABLES (8.3: "Los movimientos son inmutables... Si
existe un error, se corrige con un nuevo movimiento"). Nunca se editan ni
se borran desde el código de negocio; ver Material.save() en services.py
para cómo se actualiza el cacheado stock_actual.
"""
from django.conf import settings
from django.db import models

from catalogo.models import Material


class Movimiento(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Ingreso de material al almacén"
        SALIDA = "SALIDA", "Salida por entrega de solicitud"
        DEVOLUCION = "DEVOLUCION", "Devolución de material"
        AJUSTE_POSITIVO = "AJUSTE_POS", "Ajuste positivo de inventario"
        AJUSTE_NEGATIVO = "AJUSTE_NEG", "Ajuste negativo de inventario (faltante / baja)"

    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    cantidad = models.PositiveIntegerField()
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos_registrados",
    )
    # Vínculo opcional al ítem de solicitud que originó el movimiento
    # (SALIDA al entregar, DEVOLUCION al devolver). Null en ENTRADA/AJUSTE manuales.
    item_solicitud = models.ForeignKey(
        "solicitudes.ItemSolicitud", on_delete=models.PROTECT, null=True, blank=True,
        related_name="movimientos",
    )
    observacion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Movimiento de stock"
        verbose_name_plural = "Movimientos de stock"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_tipo_display()} x{self.cantidad} - {self.material.codigo}"
