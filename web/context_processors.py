from notificaciones.models import Notificacion


def avisos_pendientes(request):
    """Cantidad de avisos sin leer del usuario, para la barra de navegación."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {"avisos_pendientes": Notificacion.objects.filter(destinatario=request.user, leida=False).count()}
