"""
Funciones de negocio para movimientos "manuales" de inventario: ingreso de
mercadería y ajustes (incluida la baja de material roto o vencido), ambos
reservados al Jefe de Unidad de Almacén según la Tabla N°4 de la Entrega N°2.

Los movimientos que se generan automáticamente por el circuito de
solicitudes (salida al entregar, devolución, ajuste por faltante) viven en
solicitudes/services.py, que llama a las funciones de más abajo para no
duplicar la lógica de actualizar el stock cacheado.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models import Perfil
from .models import Movimiento


def _validar_jefe_unidad_almacen(usuario):
    perfil: Perfil = getattr(usuario, "perfil", None)
    if not perfil or perfil.rol != Perfil.Rol.JEFE_UNIDAD_ALMACEN:
        raise PermissionDenied(
            "Solo el Jefe de Unidad de Almacén puede registrar ingresos o ajustes de inventario."
        )


@transaction.atomic
def registrar_ingreso(material, cantidad, usuario, observacion=""):
    """Ingreso de material al almacén (reposición desde Compras, por ejemplo)."""
    _validar_jefe_unidad_almacen(usuario)
    if cantidad <= 0:
        raise ValidationError("La cantidad de ingreso debe ser positiva.")

    mov = Movimiento.objects.create(
        material=material, tipo=Movimiento.Tipo.ENTRADA, cantidad=cantidad,
        usuario=usuario, observacion=observacion,
    )
    material.stock_actual += cantidad
    material.save(update_fields=["stock_actual"])
    return mov


@transaction.atomic
def registrar_ajuste(material, cantidad, positivo: bool, usuario, observacion):
    """
    Ajuste manual de inventario (ej. baja de material roto o vencido, o
    corrección de un conteo cíclico). Siempre requiere observación: a
    diferencia de un ingreso, un ajuste altera el stock sin que haya habido
    un movimiento físico correspondiente, así que necesita quedar explicado.
    """
    _validar_jefe_unidad_almacen(usuario)
    if cantidad <= 0:
        raise ValidationError("La cantidad del ajuste debe ser positiva.")
    if not observacion:
        raise ValidationError("Todo ajuste de inventario debe llevar una observación.")

    tipo = Movimiento.Tipo.AJUSTE_POSITIVO if positivo else Movimiento.Tipo.AJUSTE_NEGATIVO
    mov = Movimiento.objects.create(
        material=material, tipo=tipo, cantidad=cantidad, usuario=usuario, observacion=observacion,
    )
    if positivo:
        material.stock_actual += cantidad
    else:
        material.stock_actual = max(0, material.stock_actual - cantidad)
    material.save(update_fields=["stock_actual"])
    return mov
