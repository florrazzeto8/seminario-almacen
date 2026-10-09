from django.core.management.base import BaseCommand

from solicitudes.services import liberar_reservas_vencidas


class Command(BaseCommand):
    help = (
        "Notifica al solicitante y al Jefe de Unidad de las solicitudes cuya "
        "reserva de stock superó el plazo configurado sin retirarse "
        "(RESERVA_PLAZO_HORAS en settings). Pensado para correr periódicamente "
        "(cron / tarea programada)."
    )

    def handle(self, *args, **options):
        avisadas = liberar_reservas_vencidas()
        if avisadas:
            self.stdout.write(self.style.WARNING(
                f"Se notificaron {len(avisadas)} solicitud(es) con reserva vencida: {avisadas}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS("No hay reservas vencidas."))
