from django.apps import AppConfig


class TareasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tareas"
    verbose_name = "Materiales, tareas y entregas"

    def ready(self):
        from . import conexiones

        conexiones.conectar()
