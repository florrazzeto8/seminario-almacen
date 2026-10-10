"""
Vistas de la interfaz web. No contienen reglas de negocio: cada acción
llama a la función correspondiente de solicitudes/services.py o
inventario/services.py y traduce sus errores a mensajes para el usuario.
"""
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogo.models import Material
from core.models import Equipo, Maquina, Perfil
from inventario import services as inventario
from notificaciones.models import Notificacion
from presupuesto.models import PresupuestoMensual
from solicitudes import services
from solicitudes.models import ItemSolicitud, Solicitud

Rol = Perfil.Rol
ROLES_SOLICITAN = (Rol.SOLICITANTE, Rol.JEFE_UNIDAD)
ROLES_APRUEBAN = (Rol.JEFE_UNIDAD, Rol.JEFE_TALLER, Rol.GERENTE)
ROLES_ALMACEN = (Rol.OPERARIO_ALMACEN, Rol.JEFE_UNIDAD_ALMACEN)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _perfil(request):
    return getattr(request.user, "perfil", None)


def rol_requerido(*roles):
    """Restringe una vista a ciertos roles de negocio (además del login)."""
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envuelta(request, *args, **kwargs):
            perfil = _perfil(request)
            if perfil is None:
                messages.warning(
                    request,
                    "Tu usuario no tiene un perfil de negocio (rol y equipo), así que solo puede administrar. "
                    "Para probar las pantallas usá los usuarios de prueba (operario_mant, ju_mant, operario_almacen1, "
                    "ju_almacen) o asignate un perfil en Administración → Perfiles.",
                )
                return redirect("inicio")
            if perfil.rol not in roles:
                messages.error(
                    request,
                    f"Esta pantalla no está disponible para el rol {perfil.get_rol_display()}.",
                )
                return redirect("inicio")
            return vista(request, *args, **kwargs)
        return envuelta
    return decorador


def _ejecutar(request, accion, mensaje_ok):
    """Ejecuta una función de servicio y convierte sus errores en mensajes."""
    try:
        resultado = accion()
    except (ValidationError, PermissionDenied) as exc:
        detalle = getattr(exc, "messages", None)
        messages.error(request, " ".join(detalle) if detalle else str(exc))
        return None
    if mensaje_ok:
        messages.success(request, mensaje_ok)
    return resultado


def _saldo_equipo(equipo):
    """Presupuesto y saldo del mes en curso para un equipo (None si no fue cargado)."""
    hoy = timezone.localdate()
    return PresupuestoMensual.objects.filter(equipo=equipo, anio=hoy.year, mes=hoy.month).first()


def _costo_estimado(solicitud):
    return sum(
        (item.material.precio_vigente * item.cantidad_solicitada for item in solicitud.items.select_related("material")),
        start=Decimal("0"),
    )


def _equipos_que_aprueba(perfil):
    if perfil.rol == Rol.JEFE_UNIDAD:
        return Equipo.objects.filter(pk=perfil.equipo_id)
    if perfil.rol in (Rol.JEFE_TALLER, Rol.GERENTE):
        return Equipo.objects.filter(area=perfil.area)
    return Equipo.objects.none()


# ---------------------------------------------------------------------------
# Inicio y avisos
# ---------------------------------------------------------------------------

@login_required
def inicio(request):
    perfil = _perfil(request)
    if perfil is None:
        if request.user.is_staff:
            return redirect("/admin/")
        messages.error(request, "Tu usuario no tiene un perfil de negocio asociado. Contactá al administrador.")
        return redirect("logout")
    if perfil.rol in ROLES_ALMACEN:
        return redirect("tablero")
    if perfil.rol in (Rol.JEFE_TALLER, Rol.GERENTE):
        return redirect("bandeja")
    if perfil.rol == Rol.ADMIN:
        return redirect("/admin/")
    return redirect("mis_solicitudes")


@login_required
def avisos(request):
    propias = Notificacion.objects.filter(destinatario=request.user)
    if request.method == "POST":
        propias.filter(leida=False).update(leida=True)
        return redirect("avisos")
    return render(request, "web/avisos.html", {
        "avisos": propias.select_related("solicitud")[:50],
        "pendientes": propias.filter(leida=False).count(),
    })


# ---------------------------------------------------------------------------
# CU-01 Registrar solicitud
# ---------------------------------------------------------------------------

@login_required
def materiales_buscar(request):
    q = request.GET.get("q", "").strip()
    materiales = []
    if len(q) >= 2:
        materiales = Material.objects.filter(activo=True).filter(
            Q(codigo__icontains=q) | Q(descripcion__icontains=q)
        ).order_by("descripcion")[:15]
    perfil = _perfil(request)
    return render(request, "web/partials/materiales_resultados.html", {
        "materiales": materiales, "q": q,
        "ver_ubicacion": perfil is not None and perfil.rol in ROLES_ALMACEN,
        "modo": request.GET.get("modo", "solicitud"),
    })


@login_required
def material_fila(request, pk):
    material = get_object_or_404(Material, pk=pk, activo=True)
    return render(request, "web/partials/item_fila.html", {
        "material": material,
        "motivos": ItemSolicitud.Motivo.choices,
        "maquinas": Maquina.objects.filter(activa=True).select_related("equipo"),
    })


@rol_requerido(*ROLES_SOLICITAN)
def solicitud_nueva(request):
    perfil = _perfil(request)
    if request.method == "POST":
        ids = request.POST.getlist("material")
        cantidades = request.POST.getlist("cantidad")
        motivos = request.POST.getlist("motivo")
        maquinas = request.POST.getlist("maquina")
        items = []
        for i, material_id in enumerate(ids):
            try:
                cantidad = int(cantidades[i])
            except (ValueError, IndexError):
                cantidad = 0
            if cantidad <= 0:
                messages.error(request, "Todas las cantidades deben ser mayores a cero.")
                return redirect("solicitud_nueva")
            maquina_id = maquinas[i] if i < len(maquinas) else ""
            items.append({
                "material": get_object_or_404(Material, pk=material_id),
                "cantidad": cantidad,
                "motivo": motivos[i] if i < len(motivos) else ItemSolicitud.Motivo.OTRO,
                "maquina": Maquina.objects.filter(pk=maquina_id).first() if maquina_id else None,
            })
        solicitud = _ejecutar(request, lambda: services.crear_solicitud(request.user, items), None)
        if solicitud:
            messages.success(request, f"Solicitud #{solicitud.pk} registrada. Tu jefe de unidad ya fue avisado.")
            return redirect("solicitud_detalle", pk=solicitud.pk)
        return redirect("solicitud_nueva")
    return render(request, "web/solicitud_nueva.html", {"equipo": perfil.equipo})


# ---------------------------------------------------------------------------
# Mis solicitudes, detalle, cancelación y devolución (CU-05, CU-06)
# ---------------------------------------------------------------------------

@login_required
def mis_solicitudes(request):
    solicitudes = (
        Solicitud.objects.filter(solicitante=request.user)
        .select_related("equipo").prefetch_related("items__material")
    )
    return render(request, "web/mis_solicitudes.html", {"solicitudes": solicitudes})


@login_required
def solicitud_detalle(request, pk):
    solicitud = get_object_or_404(
        Solicitud.objects.select_related("equipo", "solicitante", "aprobado_por", "entregado_por", "solicitud_origen"),
        pk=pk,
    )
    perfil = _perfil(request)
    es_almacen = perfil.rol in ROLES_ALMACEN
    puede_ver = (
        solicitud.solicitante_id == request.user.id or es_almacen
        or perfil.puede_aprobar_para(solicitud.equipo) or perfil.rol == Rol.ADMIN
    )
    if not puede_ver:
        messages.error(request, "No podés ver esa solicitud.")
        return redirect("inicio")
    puede_cancelar = solicitud.esta_abierta and (
        solicitud.solicitante_id == request.user.id or es_almacen or perfil.puede_aprobar_para(solicitud.equipo)
    )
    return render(request, "web/solicitud_detalle.html", {
        "s": solicitud,
        "items": solicitud.items.select_related("material", "maquina"),
        "es_almacen": es_almacen,
        "puede_cancelar": puede_cancelar,
        "puede_aprobar": solicitud.estado == Solicitud.Estado.CREADA and perfil.puede_aprobar_para(solicitud.equipo),
        "presupuesto": _saldo_equipo(solicitud.equipo),
        "costo": _costo_estimado(solicitud),
        "derivadas": solicitud.derivadas.all(),
    })


@require_POST
@login_required
def solicitud_cancelar(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk)
    motivo = request.POST.get("motivo", "").strip()
    _ejecutar(request, lambda: services.cancelar_solicitud(solicitud, request.user, motivo),
              f"Solicitud #{solicitud.pk} cancelada. Las reservas quedaron liberadas.")
    return redirect("solicitud_detalle", pk=pk)


@require_POST
@rol_requerido(*ROLES_ALMACEN)
def item_devolver(request, pk):
    item = get_object_or_404(ItemSolicitud.objects.select_related("solicitud"), pk=pk)
    try:
        cantidad = int(request.POST.get("cantidad", "0"))
    except ValueError:
        cantidad = 0
    motivo = request.POST.get("motivo", "").strip()
    _ejecutar(request, lambda: services.registrar_devolucion(item, cantidad, motivo, request.user),
              "Devolución registrada: el material volvió al stock y el importe se reintegró al equipo.")
    return redirect("solicitud_detalle", pk=item.solicitud_id)


# ---------------------------------------------------------------------------
# CU-02 Bandeja de aprobación
# ---------------------------------------------------------------------------

@rol_requerido(*ROLES_APRUEBAN)
def bandeja(request):
    perfil = _perfil(request)
    equipos = _equipos_que_aprueba(perfil)
    pendientes = (
        Solicitud.objects.filter(estado=Solicitud.Estado.CREADA, equipo__in=equipos)
        .select_related("solicitante", "equipo").prefetch_related("items__material").order_by("fecha_creacion")
    )
    filas = []
    for s in pendientes:
        presupuesto = _saldo_equipo(s.equipo)
        costo = _costo_estimado(s)
        filas.append({
            "s": s, "costo": costo, "presupuesto": presupuesto,
            "excede": presupuesto is not None and costo > presupuesto.saldo,
        })
    resueltas = (
        Solicitud.objects.filter(equipo__in=equipos)
        .exclude(estado=Solicitud.Estado.CREADA).select_related("solicitante", "equipo")[:10]
    )
    return render(request, "web/bandeja.html", {
        "filas": filas, "resueltas": resueltas,
        "equipos": [(e, _saldo_equipo(e)) for e in equipos],
    })


@require_POST
@rol_requerido(*ROLES_APRUEBAN)
def solicitud_aprobar(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk)
    _ejecutar(request, lambda: services.aprobar_solicitud(solicitud, request.user),
              f"Solicitud #{solicitud.pk} aprobada. El stock quedó reservado y el almacén ya la ve en su tablero.")
    return redirect("bandeja")


@require_POST
@rol_requerido(*ROLES_APRUEBAN)
def solicitud_rechazar(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk)
    motivo = request.POST.get("motivo", "").strip()
    if not motivo:
        messages.error(request, "Para rechazar una solicitud hay que indicar el motivo.")
        return redirect("bandeja")
    _ejecutar(request, lambda: services.rechazar_solicitud(solicitud, request.user, motivo),
              f"Solicitud #{solicitud.pk} rechazada. El solicitante fue avisado.")
    return redirect("bandeja")


# ---------------------------------------------------------------------------
# CU-03 / CU-04 Tablero del almacén, preparación y entrega
# ---------------------------------------------------------------------------

@rol_requerido(*ROLES_ALMACEN)
def tablero(request):
    base = Solicitud.objects.select_related("solicitante", "equipo", "preparado_por").prefetch_related("items__material")
    columnas = [
        ("Aprobadas", Solicitud.Estado.APROBADA, base.filter(estado=Solicitud.Estado.APROBADA).order_by("fecha_aprobacion")),
        ("En preparación", Solicitud.Estado.EN_PREPARACION, base.filter(estado=Solicitud.Estado.EN_PREPARACION).order_by("fecha_aprobacion")),
        ("Listas para retirar", Solicitud.Estado.LISTA_PARA_RETIRAR, base.filter(estado=Solicitud.Estado.LISTA_PARA_RETIRAR).order_by("fecha_aprobacion")),
    ]
    entregadas_hoy = Solicitud.objects.filter(
        estado=Solicitud.Estado.ENTREGADA, fecha_entrega__date=timezone.localdate()
    ).count()
    return render(request, "web/tablero.html", {
        "columnas": columnas, "entregadas_hoy": entregadas_hoy, "ahora": timezone.now(),
    })


@require_POST
@rol_requerido(*ROLES_ALMACEN)
def solicitud_tomar(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk)
    _ejecutar(request, lambda: services.tomar_en_preparacion(solicitud, request.user),
              f"Tomaste la solicitud #{solicitud.pk}. Está en preparación a tu nombre.")
    return redirect("solicitud_detalle", pk=pk)


@require_POST
@rol_requerido(*ROLES_ALMACEN)
def solicitud_lista(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk)
    _ejecutar(request, lambda: services.marcar_lista_para_retirar(solicitud, request.user),
              f"Solicitud #{solicitud.pk} lista para retirar. El solicitante fue avisado.")
    return redirect("tablero")


@rol_requerido(*ROLES_ALMACEN)
def solicitud_entregar(request, pk):
    solicitud = get_object_or_404(Solicitud.objects.select_related("solicitante", "equipo"), pk=pk)
    if request.method == "POST":
        legajo = request.POST.get("legajo", "").strip()
        nombre = request.POST.get("nombre", "").strip()
        resultado = _ejecutar(
            request, lambda: services.confirmar_entrega(solicitud, request.user, legajo, nombre),
            f"Entrega de la solicitud #{solicitud.pk} registrada: stock descontado y gasto imputado al equipo {solicitud.equipo.nombre}.",
        )
        if resultado:
            return redirect("tablero")
    return render(request, "web/entrega.html", {
        "s": solicitud,
        "items": solicitud.items.select_related("material").filter(estado_item=ItemSolicitud.EstadoItem.RESERVADO),
        "legajo_sugerido": getattr(getattr(solicitud.solicitante, "perfil", None), "legajo", ""),
        "nombre_sugerido": solicitud.solicitante.get_full_name(),
    })


@require_POST
@rol_requerido(*ROLES_ALMACEN)
def item_faltante(request, pk):
    item = get_object_or_404(ItemSolicitud.objects.select_related("solicitud", "material"), pk=pk)
    codigo = request.POST.get("sustituto", "").strip()
    sustituto = Material.objects.filter(codigo=codigo, activo=True).first() if codigo else None
    if codigo and sustituto is None:
        messages.error(request, f"No existe un material activo con código {codigo}.")
        return redirect("solicitud_detalle", pk=item.solicitud_id)
    try:
        cantidad = int(request.POST.get("cantidad_sustituto") or item.cantidad_solicitada)
    except ValueError:
        cantidad = item.cantidad_solicitada
    derivada = _ejecutar(
        request, lambda: services.marcar_item_faltante(item, request.user, sustituto, cantidad), None,
    )
    if derivada:
        messages.success(request, f"Faltante registrado. Se generó la solicitud derivada #{derivada.pk} por el sustituto; el jefe de unidad ya fue avisado.")
    else:
        messages.success(request, "Faltante registrado: se ajustó el inventario y se avisó a Compras.")
    return redirect("solicitud_detalle", pk=item.solicitud_id)


# ---------------------------------------------------------------------------
# CU-07 Stock, historial e ingresos
# ---------------------------------------------------------------------------

@rol_requerido(*ROLES_ALMACEN)
def stock(request):
    q = request.GET.get("q", "").strip()
    materiales = Material.objects.filter(activo=True)
    if q:
        materiales = materiales.filter(Q(codigo__icontains=q) | Q(descripcion__icontains=q))
    return render(request, "web/stock.html", {"materiales": materiales.order_by("descripcion")[:100], "q": q})


@rol_requerido(*ROLES_ALMACEN)
def material_historial(request, pk):
    material = get_object_or_404(Material, pk=pk)
    return render(request, "web/material_historial.html", {
        "m": material,
        "movimientos": material.movimientos.select_related("usuario", "item_solicitud__solicitud")[:100],
    })


@rol_requerido(*ROLES_ALMACEN)
def ingreso(request):
    if request.method == "POST":
        codigo = request.POST.get("codigo", "").strip()
        material = Material.objects.filter(codigo=codigo, activo=True).first()
        if material is None:
            messages.error(request, f"No existe un material activo con código {codigo}.")
            return redirect("ingreso")
        try:
            cantidad = int(request.POST.get("cantidad", "0"))
        except ValueError:
            cantidad = 0
        observacion = request.POST.get("observacion", "").strip()
        tipo = request.POST.get("tipo", "ingreso")
        if tipo == "ingreso":
            _ejecutar(request, lambda: inventario.registrar_ingreso(material, cantidad, request.user, observacion),
                      f"Ingreso de {cantidad} x {material.descripcion} registrado.")
        else:
            positivo = tipo == "ajuste_pos"
            _ejecutar(request, lambda: inventario.registrar_ajuste(material, cantidad, positivo, request.user, observacion),
                      f"Ajuste de inventario registrado sobre {material.descripcion}.")
        return redirect("material_historial", pk=material.pk)
    perfil = _perfil(request)
    return render(request, "web/ingreso.html", {"es_jefe": perfil.rol == Rol.JEFE_UNIDAD_ALMACEN})
