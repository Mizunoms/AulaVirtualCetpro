from django.apps import AppConfig


class AcademicoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.academico"

    def ready(self):
        from apps.cuentas import resumen as resumen_cuentas

        from .models import Aviso, PreguntaClase

        # Lo que se borra junto con una cuenta (pantalla «Eliminar cuentas»)
        resumen_cuentas.registrar_contador(
            40, "aviso publicado", "avisos publicados", lambda u: Aviso.objects.filter(autor=u).count()
        )
        resumen_cuentas.registrar_contador(
            50, "pregunta de clase", "preguntas de clase", lambda u: PreguntaClase.objects.filter(autor=u).count()
        )
