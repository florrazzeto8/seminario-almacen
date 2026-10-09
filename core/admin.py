from django.contrib import admin

from .models import Area, Equipo, Maquina, Perfil


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "area", "activo")
    list_filter = ("area", "activo")
    search_fields = ("nombre",)
    autocomplete_fields = ("area",)


@admin.register(Maquina)
class MaquinaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "equipo", "activa")
    list_filter = ("equipo__area", "activa")
    search_fields = ("codigo", "nombre")
    autocomplete_fields = ("equipo",)


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("user", "legajo", "rol", "equipo", "area")
    list_filter = ("rol", "equipo__area")
    search_fields = ("legajo", "user__username", "user__first_name", "user__last_name")
    autocomplete_fields = ("user", "equipo", "area")
