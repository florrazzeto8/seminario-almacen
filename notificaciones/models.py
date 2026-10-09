"""
notificaciones: avisos dentro del sistema (5.1 / 8.2) y a Compras.

Compras "no es usuario" del sistema (Tabla N°4), así que sus avisos no son
una Notificacion in-app sino un envío de correo (ver notificaciones/services.py,
AvisoCompras). Separamos ambos modelos para que quede claro en el admin quién
recibe qué, tal como lo pide el documento.
"""
from django.conf import settings
from django.db import models


class Notificacion(models.Model):
    class Tipo(models.TextChoices):
        PENDIENTE_APROBACION = "PENDIENTE_APROBACION", "Solicitud pendiente de aprobación"
        SOLICITUD_RECHAZADA = "SOLICITUD_RECHAZADA", "Solicitud rechazada"
        SOLICITUD_LISTA = "SOLICITUD_LISTA", "Solicitud lista para retirar"
        RESERVA_POR_VENCER = "RESERVA_POR_VENCER", "Reserva próxima a vencer"

    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones",
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    mensaje = models.CharField(max_length=255)
    solicitud = models.ForeignKey(
        "solicitudes.Solicitud", on_delete=models.CASCADE, null=True, blank=True,
        related_name="notificaciones",
    )
    leida = models.BooleanField(default=False)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_tipo_display()} -> {self.destinatario}"


class AvisoCompras(models.Model):
    """
    Aviso por correo corporativo al Área de Compras (8.4: Compras no tiene
    usuario en el sistema). En este primer incremento, en vez de integrar un
    servidor de correo real, el envío se registra acá (ver
    notificaciones/services.py::avisar_compras) para poder auditarlo y
    probarlo sin depender de infraestructura externa.
    """

    class Motivo(models.TextChoices):
        PUNTO_REABASTECIMIENTO = "PUNTO_REABASTECIMIENTO", "Punto de reabastecimiento"
        FALTANTE = "FALTANTE", "Faltante detectado en preparación"

    material = models.ForeignKey("catalogo.Material", on_delete=models.PROTECT, related_name="avisos_compras")
    motivo = models.CharField(max_length=30, choices=Motivo.choices)
    detalle = models.CharField(max_length=255, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    enviado = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Aviso a Compras"
        verbose_name_plural = "Avisos a Compras"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_motivo_display()} - {self.material.codigo}"
