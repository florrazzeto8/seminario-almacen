"""
Carga el organigrama relevado (6.1 de la Entrega N°2) y un usuario de
prueba por cada rol de la Tabla N°4, con contraseña "almacen123" para
todos, para poder probar el circuito completo apenas se levanta el
proyecto sin tener que dar de alta cada cosa a mano desde el admin.

Uso:
    python manage.py seed_organizacion
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Area, Equipo, Maquina, Perfil

User = get_user_model()
PASSWORD = "almacen123"


@transaction.atomic
def _usuario(username, nombre, apellido, legajo, rol, equipo=None, area=None):
    user, _ = User.objects.update_or_create(
        username=username,
        defaults={"first_name": nombre, "last_name": apellido, "email": f"{username}@fabricasantaisabel.example"},
    )
    user.set_password(PASSWORD)
    user.save()
    Perfil.objects.update_or_create(
        user=user, defaults={"legajo": legajo, "rol": rol, "equipo": equipo, "area": area},
    )
    return user


class Command(BaseCommand):
    help = "Carga el organigrama (áreas, equipos, máquinas) y usuarios de prueba por rol."

    @transaction.atomic
    def handle(self, *args, **options):
        # --- Áreas -----------------------------------------------------
        area_mant, _ = Area.objects.get_or_create(nombre="Mantenimiento")
        area_prod, _ = Area.objects.get_or_create(nombre="Producción")
        area_alm, _ = Area.objects.get_or_create(nombre="Almacén")
        area_compras, _ = Area.objects.get_or_create(nombre="Compras")
        area_ing, _ = Area.objects.get_or_create(nombre="Ingeniería")

        # --- Equipos (6.1: unidades de Producción + Mantenimiento + Almacén) --
        eq_mant, _ = Equipo.objects.get_or_create(area=area_mant, nombre="Mantenimiento")
        eq_alm, _ = Equipo.objects.get_or_create(area=area_alm, nombre="Almacén")
        equipos_prod = {}
        for nombre in ("Puertas", "Periféricos", "Motores", "Sellerie 2-4", "Mecánica 1", "Sellerie 6-8", "Mecánica 3-5", "TCM"):
            eq, _ = Equipo.objects.get_or_create(area=area_prod, nombre=nombre)
            equipos_prod[nombre] = eq

        # --- Máquinas de ejemplo ----------------------------------------
        Maquina.objects.get_or_create(codigo="RB-PRT-02", defaults={"nombre": "Robot soldadura Puertas 02", "equipo": equipos_prod["Puertas"]})
        Maquina.objects.get_or_create(codigo="RB-MOT-01", defaults={"nombre": "Robot ensamble Motores 01", "equipo": equipos_prod["Motores"]})
        Maquina.objects.get_or_create(codigo="CTA-AEREA-01", defaults={"nombre": "Cadena aérea Sellería 01", "equipo": equipos_prod["Sellerie 2-4"]})

        # --- Usuarios de prueba (1 por rol de la Tabla N°4) --------------
        _usuario("operario_mant", "Juan", "Pérez", "L-1001", Perfil.Rol.SOLICITANTE, equipo=eq_mant)
        ju_mant = _usuario("ju_mant", "Mario", "López", "L-1002", Perfil.Rol.JEFE_UNIDAD, equipo=eq_mant)
        jt_mant = _usuario("jt_mant", "Elena", "Ríos", "L-1003", Perfil.Rol.JEFE_TALLER, area=area_mant)
        _usuario("gerente_mant", "Carlos", "Gómez", "L-1004", Perfil.Rol.GERENTE, area=area_mant)

        _usuario("operario_puertas", "Ana", "Suárez", "L-2001", Perfil.Rol.SOLICITANTE, equipo=equipos_prod["Puertas"])
        _usuario("ju_puertas", "Diego", "Fernández", "L-2002", Perfil.Rol.JEFE_UNIDAD, equipo=equipos_prod["Puertas"])

        _usuario("operario_almacen1", "Lucía", "Martínez", "L-3001", Perfil.Rol.OPERARIO_ALMACEN, equipo=eq_alm)
        _usuario("operario_almacen2", "Pablo", "Sosa", "L-3002", Perfil.Rol.OPERARIO_ALMACEN, equipo=eq_alm)
        _usuario("ju_almacen", "Marta", "Díaz", "L-3003", Perfil.Rol.JEFE_UNIDAD_ALMACEN, equipo=eq_alm)

        self.stdout.write(self.style.SUCCESS(
            "Organigrama y usuarios de prueba cargados. Usuarios: operario_mant, ju_mant, "
            "jt_mant, gerente_mant, operario_puertas, ju_puertas, operario_almacen1, "
            "operario_almacen2, ju_almacen. Contraseña para todos: "
            f"'{PASSWORD}'."
        ))
        self.stdout.write(
            "Recordá además crear un superusuario para entrar al admin: "
            "python manage.py createsuperuser"
        )
