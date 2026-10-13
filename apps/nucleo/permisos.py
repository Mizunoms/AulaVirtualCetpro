"""Quién puede ver qué: sesión iniciada, rol y contraseña propia.

Uso:  @exigir()  → cualquier persona con sesión;  @exigir("admin")  → solo ese rol (o varios).
"""

from functools import wraps

from django.shortcuts import redirect
from django.urls import reverse

from .utils import pagina_error


def prohibido(request):
    return pagina_error(request, "No tienes permiso para ver esta página.", 403)


def no_encontrado(request):
    return pagina_error(request, "No encontramos lo que buscas.", 404)


def exigir(*roles):
    """Exige sesión iniciada y (opcionalmente) uno de los roles indicados."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            u = request.user
            if not u.is_authenticated:
                request.session["_volver_a"] = request.get_full_path()
                return redirect("cuentas:login")
            # La contraseña que le dieron era temporal: antes de usar el aula debe elegir la suya.
            if u.debe_cambiar_clave and request.path.rstrip("/") != reverse("cuentas:nueva_clave"):
                return redirect("cuentas:nueva_clave")
            if roles and u.rol not in roles:
                return prohibido(request)
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
