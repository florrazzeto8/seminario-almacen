"""
Por ahora el único punto de entrada es el admin de Django (así se definió
para este primer incremento: backend + admin, sin interfaz propia todavía).
Cuando se sume la interfaz, acá se van a agregar las rutas de
solicitudes/urls.py, etc.
"""
from django.contrib import admin
from django.urls import path

admin.site.site_header = "Almacén de Mantenimiento — Fábrica Santa Isabel"
admin.site.site_title = "Almacén Santa Isabel"
admin.site.index_title = "Panel de administración"

urlpatterns = [
    path("admin/", admin.site.urls),
]
