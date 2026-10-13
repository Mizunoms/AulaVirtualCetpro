"""Forma de entrar al panel técnico de Django: DNI o correo.

(Las pantallas del aula comprueban la contraseña ellas mismas, con límite de intentos; ver `views.entrar`.)
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from apps.nucleo import ajustes


def normalizar_identificador(texto):
    """Devuelve ('dni', '12345678') o ('correo', 'a@b.com').

    Un correo sin «@» se completa con el dominio del CETPRO (ej. «maria» -> maria@cetpro.com).
    """
    texto = (texto or "").strip().lower()
    if len(texto) == 8 and texto.isdigit():
        return "dni", texto
    if "@" not in texto and texto:
        texto = f"{texto}@{ajustes.ajuste('dominio_correo')}"
    return "correo", texto


class DniOCorreoBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(get_user_model().USERNAME_FIELD)
        if not username or password is None:
            return None
        campo, valor = normalizar_identificador(username)
        Usuario = get_user_model()
        try:
            usuario = Usuario.objects.get(**{f"{campo}__iexact": valor})
        except Usuario.DoesNotExist:
            # Gasta el mismo tiempo que un intento real, para no revelar qué cuentas existen.
            Usuario().set_password(password)
            return None
        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None
