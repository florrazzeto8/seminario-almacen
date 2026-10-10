"""
Rutas de la interfaz web. Cada pantalla corresponde a un caso de uso de la
Entrega 3 (sección 10.2): CU-01 nueva solicitud, CU-02 bandeja, CU-03
tablero y entrega, CU-04 faltante, CU-05 cancelar, CU-06 devolución.
"""
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Solicitante (CU-01, CU-05, CU-06)
    path("solicitudes/nueva/", views.solicitud_nueva, name="solicitud_nueva"),
    path("solicitudes/", views.mis_solicitudes, name="mis_solicitudes"),
    path("solicitudes/<int:pk>/", views.solicitud_detalle, name="solicitud_detalle"),
    path("solicitudes/<int:pk>/cancelar/", views.solicitud_cancelar, name="solicitud_cancelar"),
    # Parciales HTMX
    path("materiales/buscar/", views.materiales_buscar, name="materiales_buscar"),
    path("materiales/<int:pk>/fila/", views.material_fila, name="material_fila"),
    # Jefe de unidad (CU-02)
    path("bandeja/", views.bandeja, name="bandeja"),
    path("bandeja/<int:pk>/aprobar/", views.solicitud_aprobar, name="solicitud_aprobar"),
    path("bandeja/<int:pk>/rechazar/", views.solicitud_rechazar, name="solicitud_rechazar"),
    # Almacén (CU-03, CU-04, CU-06, CU-07)
    path("almacen/tablero/", views.tablero, name="tablero"),
    path("almacen/<int:pk>/tomar/", views.solicitud_tomar, name="solicitud_tomar"),
    path("almacen/<int:pk>/lista/", views.solicitud_lista, name="solicitud_lista"),
    path("almacen/<int:pk>/entregar/", views.solicitud_entregar, name="solicitud_entregar"),
    path("almacen/items/<int:pk>/faltante/", views.item_faltante, name="item_faltante"),
    path("almacen/items/<int:pk>/devolver/", views.item_devolver, name="item_devolver"),
    path("almacen/stock/", views.stock, name="stock"),
    path("almacen/stock/<int:pk>/", views.material_historial, name="material_historial"),
    path("almacen/ingreso/", views.ingreso, name="ingreso"),
    # Presupuesto (RF25) y gasto (RF28)
    path("almacen/presupuestos/", views.presupuestos, name="presupuestos"),
    path("gastos/", views.gastos, name="gastos"),
    # Avisos
    path("avisos/", views.avisos, name="avisos"),
]
