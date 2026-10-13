from django.apps import AppConfig


class EvaluacionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.evaluacion"
    verbose_name = "Asistencia y notas"

    def ready(self):
        from . import conexiones

        conexiones.conectar()
