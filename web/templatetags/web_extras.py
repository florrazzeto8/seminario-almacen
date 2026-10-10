from django import template

register = template.Library()

ESTADO_COLOR = {
    "CREADA": "secondary",
    "APROBADA": "primary",
    "EN_PREPARACION": "warning",
    "LISTA_PARA_RETIRAR": "info",
    "ENTREGADA": "success",
    "RECHAZADA": "danger",
    "CANCELADA": "dark",
}


@register.filter
def estado_color(estado):
    return ESTADO_COLOR.get(estado, "secondary")


@register.filter
def pesos(valor):
    try:
        return f"$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return valor
