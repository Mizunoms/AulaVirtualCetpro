from django.apps import AppConfig


class MensajesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mensajes"
    verbose_name = "Mensajes"

    def ready(self):
        from apps.academico import resumen
        from apps.nucleo import menu

        from .models import Mensaje

        menu.registrar_contador("mensajes", Mensaje.sin_leer)  # el número del menú «Mensajes»
        resumen.registrar_contador("mensaje", "mensajes", lambda m: Mensaje.objects.filter(conversacion__modulo=m).count())
