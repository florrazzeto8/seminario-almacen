"""
Funciones de envío de notificaciones. Centralizadas acá para que
solicitudes/services.py no tenga que saber cómo se construye cada mensaje.
"""
from django.core.mail import send_mail

from .models import AvisoCompras, Notificacion


def notificar(destinatario, tipo, mensaje, solicitud=None):
    return Notificacion.objects.create(
        destinatario=destinatario, tipo=tipo, mensaje=mensaje, solicitud=solicitud,
    )


def avisar_compras(material, motivo, detalle=""):
    """
    Registra el aviso y dispara el envío de correo. send_mail usa el backend
    configurado en settings (por defecto, consola en desarrollo -- ver
    EMAIL_BACKEND en config/settings.py) así que no requiere credenciales
    reales para probarse.
    """
    aviso = AvisoCompras.objects.create(material=material, motivo=motivo, detalle=detalle)
    try:
        send_mail(
            subject=f"[Almacén Santa Isabel] {aviso.get_motivo_display()}: {material.codigo}",
            message=(
                f"Material: {material.codigo} - {material.descripcion}\n"
                f"Motivo: {aviso.get_motivo_display()}\n"
                f"Stock disponible: {material.stock_disponible}\n"
                f"Punto de reabastecimiento: {material.punto_reabastecimiento}\n"
                f"Detalle: {detalle}"
            ),
            from_email=None,
            recipient_list=["compras@fabricasantaisabel.example"],
            fail_silently=False,
        )
        aviso.enviado = True
        aviso.save(update_fields=["enviado"])
    except Exception:
        # No queremos que una falla de correo frene el flujo de almacén;
        # el aviso queda igual registrado con enviado=False para reintentar.
        pass
    return aviso
