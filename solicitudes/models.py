"""
solicitudes: el corazón del sistema. Modela el circuito completo descrito en
8.2/8.3 de la Entrega N°2:

    Creada -> Aprobada -> En preparación -> Lista para retirar -> Entregada
       |         |
       v         v
   (Rechazada) (Cancelada, mientras no esté Entregada)

Un ítem puede además quedar Faltante durante la preparación, lo que dispara
una Solicitud derivada por el material sustituto (sin frenar el resto de la
solicitud original).

Toda la lógica que cambia de estado vive en services.py, NUNCA en este
archivo: los modelos solo describen la forma de los datos, no las reglas.
"""
from django.conf import settings
from django.db import models

from catalogo.models import Material
from core.models import Equipo, Maquina


class Solicitud(models.Model):
    class Estado(models.TextChoices):
        CREADA = "CREADA", "Creada"
        APROBADA = "APROBADA", "Aprobada"
        RECHAZADA = "RECHAZADA", "Rechazada"
        CANCELADA = "CANCELADA", "Cancelada"
        EN_PREPARACION = "EN_PREPARACION", "En preparación"
        LISTA_PARA_RETIRAR = "LISTA_PARA_RETIRAR", "Lista para retirar"
        ENTREGADA = "ENTREGADA", "Entregada"

    ESTADOS_ABIERTOS = (Estado.CREADA, Estado.APROBADA, Estado.EN_PREPARACION, Estado.LISTA_PARA_RETIRAR)
    ESTADOS_CERRADOS = (Estado.RECHAZADA, Estado.CANCELADA, Estado.ENTREGADA)

    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="solicitudes_creadas",
    )
    equipo = models.ForeignKey(
        Equipo, on_delete=models.PROTECT, related_name="solicitudes",
        help_text="Equipo al que se imputa el gasto. Se completa automáticamente "
                   "con el equipo del solicitante al crear la solicitud.",
    )
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.CREADA)

    # Trazabilidad de quién intervino en cada paso (requerida explícitamente
    # por el documento en varios puntos: 3.2, 4.3, 8.2).
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="solicitudes_aprobadas",
    )
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    preparado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="solicitudes_preparadas",
    )
    entregado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="solicitudes_entregadas",
    )
    fecha_entrega = models.DateTimeField(null=True, blank=True)
    # Quien retira físicamente el material puede no ser el solicitante
    # original (lo anota el operario de almacén en el mostrador, 8.2).
    legajo_retira = models.CharField(max_length=20, blank=True)
    nombre_retira = models.CharField(max_length=150, blank=True)

    # Plazo de reserva: si se aprueba y no se retira a tiempo, se libera
    # (8.2 / "si una reserva supera el plazo configurado sin retirarse").
    reserva_vence = models.DateTimeField(null=True, blank=True)

    # Si esta solicitud nació como reemplazo de un ítem faltante por un
    # material sustituto (8.2), queda vinculada a la solicitud original.
    solicitud_origen = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="derivadas",
    )

    class Meta:
        verbose_name = "Solicitud"
        verbose_name_plural = "Solicitudes"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"Solicitud #{self.pk} ({self.get_estado_display()}) - {self.equipo}"

    @property
    def esta_abierta(self):
        return self.estado in self.ESTADOS_ABIERTOS


class ItemSolicitud(models.Model):
    class Motivo(models.TextChoices):
        REPARACION = "REPARACION", "Reparación"
        CONSUMIBLE = "CONSUMIBLE", "Consumible"
        HERRAMIENTA = "HERRAMIENTA", "Herramienta"
        EPP = "EPP", "Elemento de protección personal"
        OTRO = "OTRO", "Otro"

    class EstadoItem(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        RESERVADO = "RESERVADO", "Reservado"
        FALTANTE = "FALTANTE", "Faltante"
        ENTREGADO = "ENTREGADO", "Entregado"
        CANCELADO = "CANCELADO", "Cancelado"

    solicitud = models.ForeignKey(Solicitud, on_delete=models.CASCADE, related_name="items")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="items_solicitados")
    cantidad_solicitada = models.PositiveIntegerField()
    motivo = models.CharField(max_length=20, choices=Motivo.choices)
    maquina = models.ForeignKey(
        Maquina, on_delete=models.PROTECT, null=True, blank=True, related_name="items_solicitados",
        help_text="Solo si el motivo es Reparación (8.3).",
    )

    estado_item = models.CharField(max_length=12, choices=EstadoItem.choices, default=EstadoItem.PENDIENTE)
    cantidad_reservada = models.PositiveIntegerField(default=0)
    cantidad_entregada = models.PositiveIntegerField(default=0)
    cantidad_devuelta = models.PositiveIntegerField(default=0)

    # Precio al momento de la entrega, para que el gasto imputado no cambie
    # retroactivamente si después se actualiza el precio_vigente del material.
    precio_unitario_entrega = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Si este ítem quedó Faltante y se generó una solicitud derivada con un
    # material sustituto, queda referenciada acá.
    item_sustituto_de = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="sustitutos",
    )

    class Meta:
        verbose_name = "Ítem de solicitud"
        verbose_name_plural = "Ítems de solicitud"

    def __str__(self):
        return f"{self.cantidad_solicitada} x {self.material.codigo} (Solicitud #{self.solicitud_id})"

    @property
    def cantidad_pendiente_devolucion(self):
        return self.cantidad_entregada - self.cantidad_devuelta
