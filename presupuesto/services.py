"""
Lógica de negocio del presupuesto: carga mensual por equipo (RF25) y
consulta del gasto por equipo y motivo (RF28). El monto lo define
Ingeniería fuera del sistema; acá solo se registra.
"""
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum

from core.models import Equipo, Perfil
from solicitudes.models import ItemSolicitud

from .models import GastoEquipo, PresupuestoMensual


def cargar_presupuesto(equipo: Equipo, anio: int, mes: int, monto, usuario) -> PresupuestoMensual:
    perfil = getattr(usuario, "perfil", None)
    if perfil is None or perfil.rol != Perfil.Rol.JEFE_UNIDAD_ALMACEN:
        raise PermissionDenied("Solo el Jefe de Unidad de Almacén registra el presupuesto mensual.")
    if not (1 <= int(mes) <= 12):
        raise ValidationError("El mes debe estar entre 1 y 12.")
    try:
        monto = Decimal(str(monto))
    except Exception:
        raise ValidationError("El monto no es válido.")
    if monto < 0:
        raise ValidationError("El monto no puede ser negativo.")
    presupuesto, _ = PresupuestoMensual.objects.update_or_create(
        equipo=equipo, anio=int(anio), mes=int(mes),
        defaults={"monto_asignado": monto, "cargado_por": usuario},
    )
    return presupuesto


def equipos_consultables(perfil: Perfil):
    """Qué equipos puede consultar cada rol (RF28)."""
    if perfil.rol == Perfil.Rol.JEFE_UNIDAD_ALMACEN:
        return Equipo.objects.filter(activo=True)
    if perfil.rol == Perfil.Rol.JEFE_UNIDAD:
        return Equipo.objects.filter(pk=perfil.equipo_id)
    if perfil.rol in (Perfil.Rol.JEFE_TALLER, Perfil.Rol.GERENTE):
        return Equipo.objects.filter(area=perfil.area, activo=True)
    return Equipo.objects.none()


def gasto_por_motivo(equipo: Equipo, anio: int, mes: int):
    """Gasto neto del mes agrupado por motivo, más el detalle de ítems."""
    gastos = GastoEquipo.objects.filter(equipo=equipo, anio=anio, mes=mes)
    etiquetas = dict(ItemSolicitud.Motivo.choices)
    por_motivo = [
        {"motivo": etiquetas.get(fila["motivo"], fila["motivo"]), "monto": fila["total"]}
        for fila in gastos.values("motivo").annotate(total=Sum("monto")).order_by("-total")
    ]
    total = gastos.aggregate(total=Sum("monto"))["total"] or Decimal("0")
    detalle = gastos.select_related("item_solicitud__material", "item_solicitud__solicitud").order_by("-fecha")[:100]
    presupuesto = PresupuestoMensual.objects.filter(equipo=equipo, anio=anio, mes=mes).first()
    return {"por_motivo": por_motivo, "total": total, "detalle": detalle, "presupuesto": presupuesto}
