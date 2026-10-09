"""
presupuesto: presupuesto mensual por equipo y su consumo.

Importante (4.4 / No contempla): el sistema NO calcula ni reparte el monto
asignado a cada equipo -- eso lo define el Área de Ingeniería por fuera del
sistema. Acá solo se registra ese monto (carga manual del Jefe de Unidad de
Almacén) y se descuenta automáticamente con cada entrega/devolución.
"""
from django.conf import settings
from django.db import models

from core.models import Equipo


class PresupuestoMensual(models.Model):
    equipo = models.ForeignKey(Equipo, on_delete=models.PROTECT, related_name="presupuestos")
    anio = models.PositiveIntegerField()
    mes = models.PositiveSmallIntegerField()
    monto_asignado = models.DecimalField(max_digits=12, decimal_places=2)
    cargado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="presupuestos_cargados",
        help_text="Debe ser el Jefe de Unidad de Almacén (Tabla N°4).",
    )
    fecha_carga = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Presupuesto mensual"
        verbose_name_plural = "Presupuestos mensuales"
        unique_together = ("equipo", "anio", "mes")
        ordering = ["-anio", "-mes", "equipo__nombre"]

    def __str__(self):
        return f"{self.equipo} {self.mes:02d}/{self.anio}: ${self.monto_asignado}"

    @property
    def gasto_neto(self):
        """Suma de gastos del mes menos reintegros por devolución, en pesos."""
        agregados = self.equipo.gastos.filter(anio=self.anio, mes=self.mes)
        total = sum((g.monto for g in agregados), start=0)
        return total

    @property
    def saldo(self):
        return self.monto_asignado - self.gasto_neto


class GastoEquipo(models.Model):
    """
    Registro de gasto (o reintegro, con monto negativo) imputado a un
    equipo. Se crea automáticamente al entregar un ítem de solicitud o al
    registrar una devolución (ver solicitudes/services.py). No se edita
    a mano: es el detalle que respalda el saldo de PresupuestoMensual.
    """

    equipo = models.ForeignKey(Equipo, on_delete=models.PROTECT, related_name="gastos")
    anio = models.PositiveIntegerField()
    mes = models.PositiveSmallIntegerField()
    monto = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Positivo = gasto por entrega. Negativo = reintegro por devolución.",
    )
    motivo = models.CharField(max_length=20)  # catalogo.Material.Motivo, como texto libre
    item_solicitud = models.ForeignKey(
        "solicitudes.ItemSolicitud", on_delete=models.PROTECT, related_name="gastos_generados",
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gasto de equipo"
        verbose_name_plural = "Gastos de equipo"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.equipo} {self.mes:02d}/{self.anio}: ${self.monto} ({self.motivo})"
