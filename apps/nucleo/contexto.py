"""Datos que todas las plantillas necesitan: ajustes, tema, menú, preferencias y avisos."""

import hashlib
from urllib.parse import quote

from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from . import ajustes
from .menu import contar, menu_de, url_o_numeral
from .utils import fecha_larga, url_absoluta, whatsapp_url


def tema_actual(request):
    """Tema de colores de este dispositivo: «claro» (por defecto) u «oscuro». Se recuerda en una cookie."""
    return "oscuro" if request.COOKIES.get("aula_tema") == "oscuro" else "claro"


def version(texto):
    """Pequeña marca para que el navegador recargue una imagen cuando cambia."""
    return hashlib.md5(texto.encode("utf-8")).hexdigest()[:8]  # noqa: S324 - no es seguridad, solo caché


def logo_url():
    """Dirección del logo (el subido en Ajustes o el del CETPRO)."""
    subido = ajustes.ajuste("logo")
    if subido:
        return f"{reverse('nucleo:marca_logo')}?v={version(subido)}"
    return static("img/logo-cetpro.png")


def fondo_login_url():
    subido = ajustes.ajuste("fondo_login")
    return f"{reverse('nucleo:marca_fondo')}?v={version(subido)}" if subido else ""


def foto_especialidad(especialidad):
    """Foto del taller de una especialidad (la sube el admin en Ajustes), o None."""
    for esp in ajustes.especialidades():
        if esp["nombre"] == especialidad and esp.get("foto"):
            return f"{reverse('nucleo:marca_especialidad')}?n={quote(especialidad)}&v={version(esp['foto'])}"
    return None


def _clases(pref):
    body = [
        c
        for c in (
            "alto-contraste" if pref.alto_contraste else "",
            "voz" if pref.lectura_voz else "",
            "sin-animacion" if pref.reducir_movimiento else "",
        )
        if c
    ]
    return (f"letra-{pref.tamano_letra}" if pref.tamano_letra != "normal" else ""), " ".join(body)


def aula(request):
    """Context processor: variables comunes del marco."""
    aj = ajustes.todas()
    usuario = request.user
    contexto = {
        "aj": aj,
        "tema": tema_actual(request),
        "tema_css": ajustes.tema_css(),
        "old": request.session.pop("_old", {}),
        "hoy_texto": fecha_larga(timezone.localtime()),
        "logo_url": logo_url(),
        "fondo_login_url": fondo_login_url(),
        "pref": None,
        "clase_html": "",
        "clases_body": "",
        "menu": [],
        "sin_leer": 0,
    }
    if usuario.is_authenticated:
        pref = usuario.preferencias
        contexto["pref"] = pref
        contexto["clase_html"], contexto["clases_body"] = _clases(pref)
        contexto["menu"] = menu_de(usuario)
        contexto["sin_leer"] = contar("avisos", usuario)
        contexto["url_avisos"] = url_o_numeral("nucleo:avisos")
        # Contraseña temporal sin cambiar (tocó «Más tarde»): aviso con el botón para crearla, en todas las pantallas menos en la suya
        contexto["clave_pendiente"] = usuario.debe_cambiar_clave and request.path.rstrip("/") != reverse("cuentas:nueva_clave")
        clave_otro = request.session.pop("_clave_otro", None)
        if isinstance(clave_otro, dict):
            texto = (
                f"Aula virtual del {aj['centro_nombre']}\n"
                f"Entra en: {url_absoluta(request, reverse('cuentas:login'))}\n"
                f"Usuario: {clave_otro['usuario']}\nContraseña: {clave_otro['clave']}"
            )
            if clave_otro.get("forzar"):
                texto += "\nAl entrar por primera vez te pedirá elegir tu propia contraseña."
            wa = (whatsapp_url(clave_otro.get("telefono")) or "https://wa.me/") + "?text=" + quote(texto, safe="")
            contexto["clave_otro"] = {**clave_otro, "texto": texto, "wa": wa}
    return contexto
