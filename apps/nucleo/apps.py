from django.apps import AppConfig


class NucleoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.nucleo"

    def ready(self):
        from . import menu
        from .models import Notificacion

        # El número rojo de la campana
        menu.registrar_contador("avisos", Notificacion.sin_leer)
