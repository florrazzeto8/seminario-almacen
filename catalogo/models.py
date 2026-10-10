"""
catalogo: el catálogo de materiales no productivos del almacén.

El campo `codigo` coincide con la columna "Material" del export de SAP que
usamos para la carga inicial (ver catalogo/management/commands/seed_catalogo.py
y Stock_de_almacen.xlsx). Algunos códigos son numéricos (ej. 5031451562) y
otros alfanuméricos (ej. R100810468), por eso es CharField y no entero.
"""
from django.db import models


class Material(models.Model):
    class Motivo(models.TextChoices):
        REPARACION = "REPARACION", "Reparación"
        HERRAMIENTA = "HERRAMIENTA", "Herramienta"
        EPP = "EPP", "Elemento de protección personal"
        CONSUMIBLE = "CONSUMIBLE", "Consumible"
        OTRO = "OTRO", "Otro"

    codigo = models.CharField(max_length=40, unique=True)
    descripcion = models.CharField(max_length=255)
    categoria = models.CharField(
        max_length=20, choices=Motivo.choices, default=Motivo.OTRO,
        help_text="Clasificación usada también como 'motivo' por defecto al "
                   "pedir el material, y para los reportes de gasto por motivo.",
    )
    unidad_medida = models.CharField(max_length=10, default="UN")

    # Ubicación física (5.1 / tarjetas de estantería: CALLE / ESTANTERÍA / ESTANTE)
    calle = models.CharField(max_length=10, blank=True)
    estanteria = models.CharField(max_length=10, blank=True)
    estante = models.CharField(max_length=10, blank=True)

    # Stock cacheado: se recalcula desde inventario.Movimiento (ver
    # inventario/services.py). Se guarda acá para que las consultas de
    # disponibilidad no tengan que sumar todo el historial en cada pedido.
    stock_actual = models.IntegerField(default=0)
    stock_reservado = models.IntegerField(default=0)
    punto_reabastecimiento = models.IntegerField(
        default=0, help_text="Nivel mínimo. Por debajo de esto se avisa a Compras.",
    )
    precio_vigente = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    activo = models.BooleanField(
        default=True,
        help_text="Los materiales que dejan de usarse se desactivan, no se borran "
                   "(4.3 / historial de stock).",
    )

    class Meta:
        verbose_name = "Material"
        verbose_name_plural = "Materiales"
        ordering = ["descripcion"]

    def __str__(self):
        return f"{self.codigo} - {self.descripcion}"

    @property
    def stock_disponible(self) -> int:
        """Stock físico menos lo ya reservado por solicitudes aprobadas."""
        return self.stock_actual - self.stock_reservado

    @property
    def stock_critico(self) -> bool:
        return self.stock_disponible <= self.punto_reabastecimiento
