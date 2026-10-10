"""
Toda la lógica de negocio del circuito de solicitudes vive acá, nunca en los
modelos ni en las vistas. Cada función corresponde a una transición de
estado descrita en 8.2/8.3 de la Entrega N°2, y hace tres cosas siempre
juntas: valida el permiso de quien la ejecuta, aplica el efecto sobre stock
o presupuesto si corresponde, y deja la notificación del caso.

Nomenclatura de los dos tipos de "faltante" que menciona el documento,
porque es fácil confundirlos:

  * Faltante AL APROBAR: el stock lógico ya era insuficiente cuando el JU
    aprueba. No hay discrepancia que corregir, es un faltante legítimo.
  * Faltante EN PREPARACIÓN: el sistema decía que había stock reservado,
    pero el operario de almacén no lo encuentra físicamente. Esto SÍ dispara
    un ajuste de inventario (es, literalmente, el "stock fantasma" que
    origina todo este proyecto) además del aviso a Compras.
"""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import Perfil
from inventario.models import Movimiento
from notificaciones.models import AvisoCompras, Notificacion
from notificaciones.services import avisar_compras, notificar
from presupuesto.models import GastoEquipo

from .models import ItemSolicitud, Solicitud

RESERVA_PLAZO_HORAS = getattr(settings, "RESERVA_PLAZO_HORAS", 12)


# ---------------------------------------------------------------------------
# Helpers de permisos
# ---------------------------------------------------------------------------

def _perfil(usuario) -> Perfil:
    perfil = getattr(usuario, "perfil", None)
    if perfil is None:
        raise PermissionDenied("El usuario no tiene un perfil de negocio asociado.")
    return perfil


def _jefe_unidad_de(equipo):
    """Devuelve el usuario Jefe de Unidad vigente de un equipo, si existe."""
    perfil = Perfil.objects.filter(rol=Perfil.Rol.JEFE_UNIDAD, equipo=equipo).select_related("user").first()
    return perfil.user if perfil else None


# ---------------------------------------------------------------------------
# 1. Creación de la solicitud
# ---------------------------------------------------------------------------

@transaction.atomic
def crear_solicitud(solicitante, items):
    """
    items: lista de dicts con las claves
        material (Material), cantidad (int), motivo (ItemSolicitud.Motivo),
        maquina (Maquina | None)
    """
    perfil = _perfil(solicitante)
    if perfil.rol not in (Perfil.Rol.SOLICITANTE, Perfil.Rol.JEFE_UNIDAD):
        raise PermissionDenied("Este usuario no puede crear solicitudes de material.")
    if not perfil.equipo:
        raise ValidationError("El solicitante no tiene un equipo asignado.")
    if not items:
        raise ValidationError("La solicitud debe tener al menos un ítem.")

    solicitud = Solicitud.objects.create(solicitante=solicitante, equipo=perfil.equipo)
    for data in items:
        if data["motivo"] == ItemSolicitud.Motivo.REPARACION and not data.get("maquina"):
            raise ValidationError("Las solicitudes por reparación deben indicar la máquina de destino.")
        ItemSolicitud.objects.create(
            solicitud=solicitud,
            material=data["material"],
            cantidad_solicitada=data["cantidad"],
            motivo=data["motivo"],
            maquina=data.get("maquina"),
        )

    ju = _jefe_unidad_de(solicitud.equipo)
    if ju:
        notificar(
            ju, Notificacion.Tipo.PENDIENTE_APROBACION,
            f"Solicitud #{solicitud.pk} de {solicitante.get_full_name() or solicitante.username} "
            f"pendiente de aprobación.",
            solicitud=solicitud,
        )
    return solicitud


# ---------------------------------------------------------------------------
# 2. Aprobación / rechazo
# ---------------------------------------------------------------------------

@transaction.atomic
def aprobar_solicitud(solicitud: Solicitud, usuario):
    perfil = _perfil(usuario)
    if not perfil.puede_aprobar_para(solicitud.equipo):
        raise PermissionDenied("Este usuario no puede aprobar solicitudes de este equipo.")
    if solicitud.estado != Solicitud.Estado.CREADA:
        raise ValidationError("Solo se puede aprobar una solicitud en estado Creada.")

    for item in solicitud.items.select_related("material"):
        material = item.material
        if material.stock_disponible >= item.cantidad_solicitada:
            material.stock_reservado += item.cantidad_solicitada
            material.save(update_fields=["stock_reservado"])
            item.cantidad_reservada = item.cantidad_solicitada
            item.estado_item = ItemSolicitud.EstadoItem.RESERVADO
        else:
            item.estado_item = ItemSolicitud.EstadoItem.FALTANTE
            avisar_compras(
                material, AvisoCompras.Motivo.FALTANTE,
                detalle=f"Stock insuficiente al aprobar la Solicitud #{solicitud.pk}.",
            )
        item.save(update_fields=["cantidad_reservada", "estado_item"])

    solicitud.estado = Solicitud.Estado.APROBADA
    solicitud.aprobado_por = usuario
    solicitud.fecha_aprobacion = timezone.now()
    solicitud.reserva_vence = timezone.now() + timedelta(hours=RESERVA_PLAZO_HORAS)
    solicitud.save(update_fields=["estado", "aprobado_por", "fecha_aprobacion", "reserva_vence"])
    # A partir de acá la solicitud aparece en el tablero del almacén (es
    # simplemente la vista que filtra Solicitud.estado == APROBADA).
    return solicitud


@transaction.atomic
def rechazar_solicitud(solicitud: Solicitud, usuario):
    perfil = _perfil(usuario)
    if not perfil.puede_aprobar_para(solicitud.equipo):
        raise PermissionDenied("Este usuario no puede rechazar solicitudes de este equipo.")
    if solicitud.estado != Solicitud.Estado.CREADA:
        raise ValidationError("Solo se puede rechazar una solicitud en estado Creada.")

    solicitud.estado = Solicitud.Estado.RECHAZADA
    solicitud.aprobado_por = usuario
    solicitud.fecha_aprobacion = timezone.now()
    solicitud.save(update_fields=["estado", "aprobado_por", "fecha_aprobacion"])

    notificar(
        solicitud.solicitante, Notificacion.Tipo.SOLICITUD_RECHAZADA,
        f"Tu solicitud #{solicitud.pk} fue rechazada.", solicitud=solicitud,
    )
    return solicitud


# ---------------------------------------------------------------------------
# 3. Preparación en el almacén
# ---------------------------------------------------------------------------

def _validar_personal_almacen(usuario):
    perfil = _perfil(usuario)
    if perfil.rol not in (Perfil.Rol.OPERARIO_ALMACEN, Perfil.Rol.JEFE_UNIDAD_ALMACEN):
        raise PermissionDenied("Solo el personal de almacén puede operar el tablero.")
    return perfil


@transaction.atomic
def tomar_en_preparacion(solicitud: Solicitud, usuario):
    _validar_personal_almacen(usuario)
    if solicitud.estado != Solicitud.Estado.APROBADA:
        raise ValidationError("Solo se puede preparar una solicitud Aprobada.")

    solicitud.estado = Solicitud.Estado.EN_PREPARACION
    solicitud.preparado_por = usuario
    solicitud.save(update_fields=["estado", "preparado_por"])
    return solicitud


@transaction.atomic
def marcar_item_faltante(item: ItemSolicitud, usuario, material_sustituto=None, cantidad_sustituto=None):
    """
    El operario, al ir a buscar el material a la estantería, descubre que
    pese a estar RESERVADO no está físicamente disponible (stock fantasma).
    Corrige el inventario, libera la reserva, avisa a Compras y -- si se
    indica un material sustituto -- genera una solicitud derivada.
    """
    _validar_personal_almacen(usuario)
    if item.estado_item != ItemSolicitud.EstadoItem.RESERVADO:
        raise ValidationError("Solo se puede marcar como faltante un ítem Reservado.")
    if item.solicitud.estado != Solicitud.Estado.EN_PREPARACION:
        raise ValidationError("La solicitud debe estar En preparación.")

    material = item.material
    cantidad = item.cantidad_reservada

    # Ajuste de inventario: lo que el sistema creía que había, no estaba.
    Movimiento.objects.create(
        material=material, tipo=Movimiento.Tipo.AJUSTE_NEGATIVO, cantidad=cantidad,
        usuario=usuario, item_solicitud=item,
        observacion=f"Faltante detectado en preparación de la Solicitud #{item.solicitud_id}.",
    )
    material.stock_actual = max(0, material.stock_actual - cantidad)
    material.stock_reservado = max(0, material.stock_reservado - cantidad)
    material.save(update_fields=["stock_actual", "stock_reservado"])

    item.estado_item = ItemSolicitud.EstadoItem.FALTANTE
    item.cantidad_reservada = 0
    item.save(update_fields=["estado_item", "cantidad_reservada"])

    avisar_compras(
        material, AvisoCompras.Motivo.FALTANTE,
        detalle=f"Faltante físico detectado en preparación de la Solicitud #{item.solicitud_id}.",
    )

    if material_sustituto is not None:
        nueva = Solicitud.objects.create(
            solicitante=item.solicitud.solicitante, equipo=item.solicitud.equipo,
            solicitud_origen=item.solicitud,
        )
        ItemSolicitud.objects.create(
            solicitud=nueva, material=material_sustituto,
            cantidad_solicitada=cantidad_sustituto or cantidad,
            motivo=item.motivo, maquina=item.maquina, item_sustituto_de=item,
        )
        ju = _jefe_unidad_de(nueva.equipo)
        if ju:
            notificar(
                ju, Notificacion.Tipo.PENDIENTE_APROBACION,
                f"Solicitud derivada #{nueva.pk} (sustituto de ítem faltante) pendiente de aprobación.",
                solicitud=nueva,
            )
        return nueva
    return None


@transaction.atomic
def marcar_lista_para_retirar(solicitud: Solicitud, usuario):
    _validar_personal_almacen(usuario)
    if solicitud.estado != Solicitud.Estado.EN_PREPARACION:
        raise ValidationError("Solo se puede marcar lista una solicitud En preparación.")
    if not solicitud.items.filter(estado_item=ItemSolicitud.EstadoItem.RESERVADO).exists():
        raise ValidationError("La solicitud no tiene ítems reservados para entregar.")

    solicitud.estado = Solicitud.Estado.LISTA_PARA_RETIRAR
    solicitud.save(update_fields=["estado"])

    notificar(
        solicitud.solicitante, Notificacion.Tipo.SOLICITUD_LISTA,
        f"Tu solicitud #{solicitud.pk} está lista para retirar.", solicitud=solicitud,
    )
    return solicitud


# ---------------------------------------------------------------------------
# 4. Entrega y devolución
# ---------------------------------------------------------------------------

@transaction.atomic
def confirmar_entrega(solicitud: Solicitud, usuario, legajo_retira, nombre_retira=""):
    _validar_personal_almacen(usuario)
    if solicitud.estado != Solicitud.Estado.LISTA_PARA_RETIRAR:
        raise ValidationError("Solo se puede entregar una solicitud Lista para retirar.")
    if not legajo_retira:
        raise ValidationError("Debe registrarse el legajo de quien retira el material.")

    ahora = timezone.now()
    for item in solicitud.items.select_related("material").filter(estado_item=ItemSolicitud.EstadoItem.RESERVADO):
        material = item.material
        cantidad = item.cantidad_reservada

        Movimiento.objects.create(
            material=material, tipo=Movimiento.Tipo.SALIDA, cantidad=cantidad,
            usuario=usuario, item_solicitud=item,
            observacion=f"Entrega Solicitud #{solicitud.pk}.",
        )
        material.stock_actual -= cantidad
        material.stock_reservado -= cantidad
        material.save(update_fields=["stock_actual", "stock_reservado"])

        item.cantidad_entregada = cantidad
        item.estado_item = ItemSolicitud.EstadoItem.ENTREGADO
        item.precio_unitario_entrega = material.precio_vigente
        item.save(update_fields=["cantidad_entregada", "estado_item", "precio_unitario_entrega"])

        GastoEquipo.objects.create(
            equipo=solicitud.equipo, anio=ahora.year, mes=ahora.month,
            monto=material.precio_vigente * cantidad, motivo=item.motivo, item_solicitud=item,
        )

        if material.stock_critico:
            avisar_compras(
                material, AvisoCompras.Motivo.PUNTO_REABASTECIMIENTO,
                detalle=f"Stock disponible ({material.stock_disponible}) en o por debajo del "
                        f"punto de reabastecimiento ({material.punto_reabastecimiento}).",
            )

    solicitud.estado = Solicitud.Estado.ENTREGADA
    solicitud.entregado_por = usuario
    solicitud.fecha_entrega = ahora
    solicitud.legajo_retira = legajo_retira
    solicitud.nombre_retira = nombre_retira
    solicitud.save(update_fields=["estado", "entregado_por", "fecha_entrega", "legajo_retira", "nombre_retira"])
    return solicitud


@transaction.atomic
def registrar_devolucion(item: ItemSolicitud, cantidad, motivo, usuario):
    _validar_personal_almacen(usuario)
    if cantidad <= 0:
        raise ValidationError("La cantidad a devolver debe ser positiva.")
    if cantidad > item.cantidad_pendiente_devolucion:
        raise ValidationError("No se puede devolver más de lo entregado y no devuelto.")

    material = item.material
    Movimiento.objects.create(
        material=material, tipo=Movimiento.Tipo.DEVOLUCION, cantidad=cantidad,
        usuario=usuario, item_solicitud=item, observacion=motivo,
    )
    material.stock_actual += cantidad
    material.save(update_fields=["stock_actual"])

    item.cantidad_devuelta += cantidad
    item.save(update_fields=["cantidad_devuelta"])

    ahora = timezone.now()
    precio = item.precio_unitario_entrega or material.precio_vigente
    GastoEquipo.objects.create(
        equipo=item.solicitud.equipo, anio=ahora.year, mes=ahora.month,
        monto=-(precio * cantidad), motivo=item.motivo, item_solicitud=item,
    )
    return item


# ---------------------------------------------------------------------------
# 5. Cancelación y reservas vencidas
# ---------------------------------------------------------------------------

@transaction.atomic
def cancelar_solicitud(solicitud: Solicitud, usuario):
    perfil = _perfil(usuario)
    es_titular = solicitud.solicitante_id == usuario.id
    puede_por_rol = perfil.rol in (Perfil.Rol.OPERARIO_ALMACEN, Perfil.Rol.JEFE_UNIDAD_ALMACEN) or (
        perfil.puede_aprobar_para(solicitud.equipo)
    )
    if not (es_titular or puede_por_rol):
        raise PermissionDenied("Este usuario no puede cancelar esta solicitud.")
    if not solicitud.esta_abierta:
        raise ValidationError("Solo se puede cancelar una solicitud que no esté Entregada, Rechazada o ya Cancelada.")

    for item in solicitud.items.select_related("material").filter(
        estado_item__in=(ItemSolicitud.EstadoItem.RESERVADO, ItemSolicitud.EstadoItem.PENDIENTE)
    ):
        if item.cantidad_reservada:
            material = item.material
            material.stock_reservado = max(0, material.stock_reservado - item.cantidad_reservada)
            material.save(update_fields=["stock_reservado"])
        item.cantidad_reservada = 0
        item.estado_item = ItemSolicitud.EstadoItem.CANCELADO
        item.save(update_fields=["cantidad_reservada", "estado_item"])

    solicitud.estado = Solicitud.Estado.CANCELADA
    solicitud.save(update_fields=["estado"])
    return solicitud


def liberar_reservas_vencidas(ahora=None):
    """
    Pensada para correr periódicamente (management command / cron). El
    documento solo pide que el sistema NOTIFIQUE al vencer el plazo de
    reserva, no que cancele automáticamente -- la cancelación efectiva
    queda en manos de un humano vía cancelar_solicitud().
    """
    ahora = ahora or timezone.now()
    vencidas = Solicitud.objects.filter(
        estado__in=(Solicitud.Estado.APROBADA, Solicitud.Estado.EN_PREPARACION, Solicitud.Estado.LISTA_PARA_RETIRAR),
        reserva_vence__lt=ahora,
    )
    avisadas = []
    for solicitud in vencidas:
        notificar(
            solicitud.solicitante, Notificacion.Tipo.RESERVA_POR_VENCER,
            f"La reserva de tu solicitud #{solicitud.pk} venció. Contactá al almacén.",
            solicitud=solicitud,
        )
        ju = _jefe_unidad_de(solicitud.equipo)
        if ju:
            notificar(
                ju, Notificacion.Tipo.RESERVA_POR_VENCER,
                f"La reserva de la solicitud #{solicitud.pk} de tu equipo venció.", solicitud=solicitud,
            )
        avisadas.append(solicitud.pk)
    return avisadas
