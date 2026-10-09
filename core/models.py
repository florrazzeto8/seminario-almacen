"""
core: estructura organizacional de la Fábrica Santa Isabel.

Modela el organigrama relevado en la Entrega N°2 (punto 6.1):
Área -> (Gerente, Jefe de Taller) -> Equipo -> (Jefe de Unidad, Operarios)

Un "Equipo" es la unidad que tiene presupuesto propio (cuenta de costos) y a
la que se imputa cada material entregado. Coincide con lo que el documento
llama "equipo" al hablar de presupuesto y con las "Unidades" del organigrama
(Puertas, Motores, Mantenimiento, Almacén, etc.).
"""
from django.conf import settings
from django.db import models


class Area(models.Model):
    """Mantenimiento, Producción, Almacén, Compras, Ingeniería."""

    nombre = models.CharField(max_length=80, unique=True)

    class Meta:
        verbose_name = "Área"
        verbose_name_plural = "Áreas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Equipo(models.Model):
    """
    Unidad con presupuesto propio (cuenta de costos). Ej: "Mantenimiento",
    "Puertas", "Motores", "Sellerie 2-4", "Almacén".

    No todos los equipos solicitan material: el equipo "Almacén" existe
    para que el personal de almacén tenga un Perfil asociado, pero no
    participa del circuito de solicitud/aprobación.
    """

    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="equipos")
    nombre = models.CharField(max_length=120)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Equipo"
        verbose_name_plural = "Equipos"
        unique_together = ("area", "nombre")
        ordering = ["area__nombre", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.area.nombre})"


class Maquina(models.Model):
    """
    Máquina o robot de la planta. Se referencia opcionalmente en un ítem de
    solicitud cuando el motivo es 'Reparación' (ver solicitudes.ItemSolicitud).
    """

    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=150)
    equipo = models.ForeignKey(
        Equipo, on_delete=models.PROTECT, related_name="maquinas",
        help_text="Equipo/sector de producción o mantenimiento al que pertenece.",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Máquina"
        verbose_name_plural = "Máquinas"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class Perfil(models.Model):
    """
    Extiende al User de Django con el rol de negocio y su ubicación en el
    organigrama. Un usuario de Django = una persona real de la planta.

    Roles (Tabla N°4 de la Entrega N°2):
      SOLICITANTE            -> Operario de Producción o Mantenimiento
      JEFE_UNIDAD             -> Jefe de Unidad de un equipo solicitante
      JEFE_TALLER              -> aprueba en reemplazo del JU de su área
      GERENTE                  -> aprueba en reemplazo del Jefe de Taller
      OPERARIO_ALMACEN        -> atiende el tablero del almacén
      JEFE_UNIDAD_ALMACEN     -> + carga presupuesto, aprueba ajustes
      ADMIN                    -> administración del sistema
    """

    class Rol(models.TextChoices):
        SOLICITANTE = "SOLICITANTE", "Solicitante"
        JEFE_UNIDAD = "JEFE_UNIDAD", "Jefe de Unidad de equipo"
        JEFE_TALLER = "JEFE_TALLER", "Jefe de Taller"
        GERENTE = "GERENTE", "Gerente de área"
        OPERARIO_ALMACEN = "OPERARIO_ALMACEN", "Operario de almacén"
        JEFE_UNIDAD_ALMACEN = "JEFE_UNIDAD_ALMACEN", "Jefe de Unidad de almacén"
        ADMIN = "ADMIN", "Administrador"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil"
    )
    legajo = models.CharField(max_length=20, unique=True)
    rol = models.CharField(max_length=24, choices=Rol.choices)

    # Un Solicitante o Jefe de Unidad de equipo pertenece a un Equipo puntual.
    equipo = models.ForeignKey(
        Equipo, on_delete=models.PROTECT, null=True, blank=True,
        related_name="miembros",
        help_text="Obligatorio para SOLICITANTE, JEFE_UNIDAD y OPERARIO_ALMACEN/"
                   "JEFE_UNIDAD_ALMACEN (su equipo es 'Almacén').",
    )
    # Un Jefe de Taller o Gerente supervisa toda un área, no un equipo puntual.
    area = models.ForeignKey(
        Area, on_delete=models.PROTECT, null=True, blank=True,
        related_name="responsables",
        help_text="Obligatorio para JEFE_TALLER y GERENTE.",
    )

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfiles"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_rol_display()})"

    def puede_aprobar_para(self, equipo: "Equipo") -> bool:
        """
        Implementa la cadena de reemplazo de aprobación (8.2):
        JU del equipo -> Jefe de Taller del área -> Gerente del área.
        """
        if self.rol == self.Rol.JEFE_UNIDAD:
            return self.equipo_id == equipo.id
        if self.rol in (self.Rol.JEFE_TALLER, self.Rol.GERENTE):
            return self.area_id == equipo.area_id
        return False
