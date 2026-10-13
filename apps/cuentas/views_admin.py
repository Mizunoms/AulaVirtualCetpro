"""Administración de personas (solo el administrador). Se completa en la fase 5; aquí lo que ya necesitan los módulos."""

from urllib.parse import quote

from django.shortcuts import redirect
from django.urls import reverse

from apps.nucleo import ajustes
from apps.nucleo.menu import url_o_numeral
from apps.nucleo.permisos import exigir
from apps.nucleo.utils import error, url_absoluta, vista, whatsapp_url

from .models import Rol


@exigir(Rol.ADMIN)
def claves_lote(request):
    """Contraseñas nuevas dadas en lote. Se muestran una sola vez."""
    lista = request.session.pop("_claves_lote", None)
    if not lista:
        error(request, "No hay contraseñas nuevas para mostrar.")
        return redirect("nucleo:inicio")
    texto = "".join(f"{x['nombre']} · Usuario: {x['usuario']} · Contraseña: {x['clave']}\n" for x in lista)
    entra_en = url_absoluta(request, reverse("cuentas:login"))
    for x in lista:
        mensaje = (
            f"Aula virtual del {ajustes.ajuste('centro_nombre')}\nEntra en: {entra_en}\nUsuario: {x['usuario']}\n"
            f"Contraseña: {x['clave']}\nAl entrar por primera vez te pedirá elegir tu propia contraseña."
        )
        x["wa"] = (whatsapp_url(x.get("telefono")) or "https://wa.me/") + "?text=" + quote(mensaje, safe="")
    return vista(
        request,
        "admin/usuarios/claves.html",
        {"lista": lista, "texto_todo": texto},
        titulo="Contraseñas nuevas",
        sub="Se muestran una sola vez",
        volver=url_o_numeral("cuentas:admin_personas"),
        menu="usuarios",
    )
