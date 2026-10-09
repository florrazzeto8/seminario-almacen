"""
Carga el catálogo inicial de materiales desde el export real de stock
(Stock_de_almacen.xlsx: columnas "Material", "Texto breve de material",
"Cantidad total reg."), en vez de usar datos inventados.

Uso:
    python manage.py seed_catalogo /ruta/a/Stock_de_almacen.xlsx

Nota sobre los datos: el archivo real trae algunas filas con cantidad
negativa (ej. -1), que es exactamente el tipo de inconsistencia que el
proyecto busca eliminar (stock registrado que no refleja la realidad).
Las cargamos en 0 y lo dejamos reportado al final, en vez de ocultarlo.
"""
import openpyxl
from django.core.management.base import BaseCommand, CommandError

from catalogo.models import Material

# Heurística simple por palabras clave para no dejar todo en "Otro".
# Es best-effort: conviene revisar y corregir la categoría manualmente
# desde el admin para los materiales más usados.
PALABRAS_EPP = ("GUANTE", "CASCO", "GAFA", "MASCARILLA", "TAPON", "CALZADO", "CHALECO", "ARNES")
PALABRAS_QUIMICO = ("ACEITE", "SOLVENTE", "LUBR", "PINTURA", "GRASA")
PALABRAS_HERRAMIENTA = ("LLAVE", "DESTORNILLADOR", "MARTILLO", "CALIBRE", "TALADRO", "PINZA")


def categorizar(descripcion: str) -> str:
    desc = descripcion.upper()
    if any(p in desc for p in PALABRAS_EPP):
        return Material.Motivo.EPP
    if any(p in desc for p in PALABRAS_QUIMICO):
        return Material.Motivo.QUIMICO
    if any(p in desc for p in PALABRAS_HERRAMIENTA):
        return Material.Motivo.HERRAMIENTA
    return Material.Motivo.OTRO


class Command(BaseCommand):
    help = "Importa el catálogo de materiales desde el Excel de stock exportado de SAP."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str, help="Ruta al .xlsx con columnas Material / Texto breve de material / Cantidad total reg.")
        parser.add_argument("--hoja", type=str, default=None, help="Nombre de la hoja (por defecto, la primera).")

    def handle(self, *args, **options):
        try:
            wb = openpyxl.load_workbook(options["archivo"], data_only=True)
        except FileNotFoundError:
            raise CommandError(f"No se encontró el archivo: {options['archivo']}")

        ws = wb[options["hoja"]] if options["hoja"] else wb.worksheets[0]
        filas = list(ws.iter_rows(min_row=2, values_only=True))  # salta encabezado

        creados, actualizados, con_stock_negativo = 0, 0, 0
        for codigo, descripcion, cantidad in filas:
            if codigo is None or descripcion is None:
                continue
            codigo = str(codigo).strip()
            descripcion = str(descripcion).strip()
            cantidad = int(cantidad or 0)

            if cantidad < 0:
                con_stock_negativo += 1
                cantidad = 0

            _, creado = Material.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "descripcion": descripcion,
                    "categoria": categorizar(descripcion),
                    "stock_actual": cantidad,
                },
            )
            creados += int(creado)
            actualizados += int(not creado)

        self.stdout.write(self.style.SUCCESS(
            f"Catálogo importado: {creados} materiales nuevos, {actualizados} actualizados."
        ))
        if con_stock_negativo:
            self.stdout.write(self.style.WARNING(
                f"{con_stock_negativo} fila(s) traían stock negativo en el export de SAP "
                f"(se cargaron en 0). Es el mismo problema de 'stock fantasma' que describe "
                f"la Introducción del proyecto -- conviene revisarlas a mano antes de salir a producción."
            ))
