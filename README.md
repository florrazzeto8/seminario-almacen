# Sistema de gestión del almacén industrial — Fábrica Santa Isabel

Backend del sistema definido en la Entrega N°2 (Seminario de Práctica de
Analista en Software). Este incremento cubre **modelos + lógica de negocio +
Django admin**, sin interfaz propia todavía (queda para el próximo paso).

## 1. Puesta en marcha

Requiere Python 3.11+ instalado.

```bash
# 1. Crear y activar un entorno virtual
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Crear las tablas
python manage.py makemigrations
python manage.py migrate

# 4. Cargar organigrama + usuarios de prueba (1 por rol, contraseña almacen123)
python manage.py seed_organizacion

# 5. Cargar el catálogo real de materiales desde el Excel de stock
python manage.py seed_catalogo /ruta/a/Stock_de_almacen.xlsx

# 6. Crear tu propio superusuario para entrar al admin
python manage.py createsuperuser

# 7. Levantar el servidor
python manage.py runserver
```

Entrar a `http://127.0.0.1:8000/admin/` con el superusuario.

Por defecto usa **SQLite** (cero configuración). Para usar PostgreSQL, como
está definido en la Entrega N°2, ver el bloque comentado en
`config/settings.py` e instalar `psycopg2-binary`.

## 2. Cómo está organizado el código

Cada app de Django corresponde a un módulo del backend descrito en 8.3:

| App             | Qué modela                                                   |
|------------------|---------------------------------------------------------------|
| `core`           | Áreas, Equipos, Máquinas y Perfil (rol de cada usuario)       |
| `catalogo`       | Material (catálogo del pañol)                                 |
| `inventario`     | Movimiento (historial inmutable de stock)                     |
| `presupuesto`    | PresupuestoMensual y GastoEquipo                               |
| `solicitudes`    | Solicitud, ItemSolicitud y **toda la lógica de negocio**      |
| `notificaciones` | Notificacion (in-app) y AvisoCompras (correo, Compras no es usuario) |

**Regla del proyecto:** los modelos (`models.py`) solo describen la forma de
los datos. Toda regla de negocio (quién puede aprobar, qué pasa al marcar un
faltante, cómo se calcula el gasto, etc.) vive en `services.py` de cada app,
sobre todo en `solicitudes/services.py`, que es el archivo más importante del
proyecto: ahí está modelada cada transición de estado de la Figura 4 del
documento (Creada → Aprobada → En preparación → Lista para retirar →
Entregada, con sus ramas de Rechazada/Cancelada/Faltante).

## 3. Cómo probar el circuito completo desde el admin

Con los usuarios de `seed_organizacion` cargados:

1. Entrá al admin como `operario_mant` (no tiene permiso de admin por
   defecto -- para probar esto rápido, dale `is_staff=True` desde el
   superusuario, o probá las funciones directo por consola, ver más abajo).
2. Más simple para probar: abrí `python manage.py shell` y ejecutá el flujo
   a mano llamando a las funciones de `solicitudes.services` (ver ejemplo
   abajo).
3. O desde `/admin/solicitudes/solicitud/`: seleccioná una solicitud en
   estado Creada y usá la acción **"Aprobar solicitudes seleccionadas"**,
   después **"Tomar en preparación"**, después **"Marcar lista para
   retirar"**, y por último **"Confirmar entrega en mostrador"`.

### Ejemplo por consola (`python manage.py shell`)

```python
from django.contrib.auth import get_user_model
from catalogo.models import Material
from solicitudes import services
from solicitudes.models import ItemSolicitud

User = get_user_model()
operario = User.objects.get(username="operario_mant")
ju = User.objects.get(username="ju_mant")
almacen = User.objects.get(username="operario_almacen1")

material = Material.objects.first()  # cualquiera del catálogo importado

solicitud = services.crear_solicitud(operario, [
    {"material": material, "cantidad": 2, "motivo": ItemSolicitud.Motivo.OTRO},
])

services.aprobar_solicitud(solicitud, ju)
services.tomar_en_preparacion(solicitud, almacen)
services.marcar_lista_para_retirar(solicitud, almacen)
services.confirmar_entrega(solicitud, almacen, legajo_retira="L-1001", nombre_retira="Juan Pérez")

solicitud.refresh_from_db()
print(solicitud.estado)  # ENTREGADA
```

## 4. Qué falta (a propósito, para el próximo incremento)

- **Interfaz propia** (formulario de solicitud, bandeja de aprobación,
  tablero del almacén): por ahora se prueba todo desde el admin, según lo
  acordado para este incremento.
- **Login contra el directorio corporativo**: por ahora son usuarios
  simples de Django (`django.contrib.auth`), como se definió para este
  incremento. El punto de enganche futuro es un backend de autenticación
  custom en `AUTHENTICATION_BACKENDS` (settings.py).
- **Envío real de correo a Compras**: el `EMAIL_BACKEND` está en modo
  consola; para producción hay que apuntarlo a un servidor SMTP real.
- **Lectura de código de barras**: el modelo de `Movimiento` ya soporta
  registrar el material por su `codigo`, pero la lectura por hardware/cámara
  es un tema de la interfaz, no del backend.

## 5. Dato sobre los datos de prueba

`seed_catalogo` importa los 1433 materiales reales del Excel de stock que
nos pasaron. Algunas filas traían cantidad **negativa** en el export de SAP
(ej. -1): son justamente el tipo de inconsistencia que describe la
Introducción del proyecto. El comando las carga en 0 y avisa cuántas
encontró, en vez de ignorarlo silenciosamente.
