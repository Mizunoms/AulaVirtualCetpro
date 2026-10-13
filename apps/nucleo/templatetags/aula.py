"""Etiquetas y filtros de plantilla comunes a todo el aula."""

from urllib.parse import urlencode

from django import template
from django.middleware.csrf import get_token
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .. import ajustes, utils
from ..contexto import foto_especialidad as _foto_especialidad
from ..contexto import tema_actual
from ..dibujos import dibujo_taller
from ..iconos import ICONOS
from ..menu import url_o_numeral

register = template.Library()


@register.simple_tag
def icono(nombre, tam=24):
    """Ícono de trazo en línea (decorativo: siempre va con texto o con aria-label)."""
    trazo = ICONOS.get(nombre, "")
    return mark_safe(  # noqa: S308 - los trazos son fijos, escritos por nosotros
        f'<svg class="icono" width="{int(tam)}" height="{int(tam)}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true" focusable="false">{trazo}</svg>'
    )


@register.simple_tag(takes_context=True)
def boton_tema(context, clase):
    """Botón para pasar de modo claro a oscuro (y al revés). `clase` da el estilo según dónde se ponga."""
    request = context["request"]
    oscuro = tema_actual(request) == "oscuro"
    from django.urls import reverse

    return format_html(
        '<form method="post" action="{}" class="form-tema">'
        '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
        '<input type="hidden" name="tema" value="{}">'
        '<input type="hidden" name="volver" value="{}">'
        '<button type="submit" class="{}">{} {}</button></form>',
        reverse("nucleo:tema"),
        get_token(request),
        "claro" if oscuro else "oscuro",
        request.get_full_path(),
        clase,
        icono("sol" if oscuro else "luna", 22),
        "Modo claro" if oscuro else "Modo oscuro",
    )


@register.simple_tag
def vacio(nombre_icono, titulo, texto="", boton=None, enlace=None, positivo=False):
    """Recuadro para cuando todavía no hay nada que mostrar: ícono, qué pasa y, si se puede, el siguiente paso."""
    return format_html(
        '<div class="vacio tarjeta{}"><span class="vacio-icono" aria-hidden="true">{}</span>'
        '<p class="vacio-titulo">{}</p>{}{}</div>',
        " vacio-ok" if positivo else "",
        icono(nombre_icono, 30),
        titulo,
        format_html('<p class="vacio-texto">{}</p>', texto) if texto else "",
        format_html('<a class="btn btn-cetpro" href="{}">{}</a>', enlace, boton) if boton and enlace else "",
    )


@register.simple_tag
def paginador(pagina, paginas, base, params=None, **filtros):
    """«Anterior», números y «Siguiente». `base` es la dirección y `params` (o los nombre=valor) los filtros que se conservan."""
    if paginas <= 1:
        return ""
    params = {**(params or {}), **filtros}

    def enlace(n, texto, clase="", extra=""):
        filtros = {k: v for k, v in {**params, "pagina": n}.items() if v not in ("", None, 0)}
        qs = urlencode(filtros)
        return format_html(
            '<a class="pag {}" href="{}"{}>{}</a>',
            clase,
            base + ("?" + qs if qs else ""),
            mark_safe(extra),
            texto,  # noqa: S308
        )

    partes = [
        enlace(pagina - 1, "‹ Anterior") if pagina > 1 else mark_safe('<span class="pag desactivado">‹ Anterior</span>')  # noqa: S308
    ]
    ultimo = 0
    for n in range(1, paginas + 1):
        if n in (1, paginas) or abs(n - pagina) <= 1:
            partes.append(enlace(n, str(n), "actual" if n == pagina else "", ' aria-current="page"' if n == pagina else ""))
            ultimo = n
        elif ultimo == n - 1:
            partes.append(mark_safe('<span class="pag-puntos" aria-hidden="true">…</span>'))  # noqa: S308
    partes.append(
        enlace(pagina + 1, "Siguiente ›") if pagina < paginas else mark_safe('<span class="pag desactivado">Siguiente ›</span>')  # noqa: S308
    )
    return format_html('<nav class="paginador" aria-label="Páginas">{}</nav>', format_html_join("", "{}", ((p,) for p in partes)))


@register.inclusion_tag("partials/pestanas_modulo.html")
def pestanas_modulo(modulo, activa, acceso):
    """Barra de secciones de un módulo (Contenido, Tareas, Mensajes, Calificaciones), igual en todas sus pantallas.
    `activa`: contenido | tareas | mensajes | notas."""
    pestanas = [
        ("contenido", "Contenido", url_o_numeral("academico:modulo", modulo.pk), "carpeta"),
        ("tareas", "Tareas", url_o_numeral("tareas:modulo", modulo.pk), "tarea"),
        ("mensajes", "Mensajes", url_o_numeral("mensajes:modulo", modulo.pk), "mensaje"),
        (
            "notas",
            "Calificaciones" if acceso == "alumno" else "Notas",
            url_o_numeral("academico:notas_modulo", modulo.pk),
            "notas",
        ),
    ]
    if acceso not in ("alumno", "docente"):
        pestanas = [p for p in pestanas if p[0] != "mensajes"]  # administración y dirección no tienen mensajes en los módulos
    return {"modulo": modulo, "activa": activa, "pestanas": pestanas}


@register.inclusion_tag("partials/portada_modulo.html")
def portada_modulo(especialidad, titulo, chip="", chip_clase="chip-ok"):
    """Portada de la tarjeta de un módulo: la foto del taller con un degradado oscuro encima o, si el administrador
    todavía no subió una, un fondo de color con degradado y el dibujo del taller."""
    return {
        "foto": _foto_especialidad(especialidad),
        "color": ajustes.color_curso(especialidad),
        "dibujo": dibujo_taller(especialidad),
        "titulo": titulo,
        "chip": chip,
        "chip_clase": chip_clase,
    }


@register.filter
def nombre_corto_modulo(modulo):
    """Nombre corto de un módulo para espacios chicos: «Panadería I», «Peluquería II»."""
    import re

    carrera = re.split(r"\s+(?:y|e)\s+", modulo.especialidad or "")[0].strip()
    numero = re.sub(r"^m[óo]dulo\s+", "", modulo.modulo or "", flags=re.I).strip()
    return f"{carrera} {numero}".strip() or modulo.nombre


@register.simple_tag
def color_curso(especialidad):
    return ajustes.color_curso(especialidad)


@register.simple_tag
def foto_especialidad(especialidad):
    return _foto_especialidad(especialidad) or ""


register.simple_tag(url_o_numeral, name="enlace")  # {% enlace 'app:nombre' arg %} → dirección, o «#» si esa parte aún no existe
register.filter("fecha_larga", utils.fecha_larga)
register.filter("fecha_corta", utils.fecha_corta)
register.filter("hora_texto", utils.hora_texto)
register.filter("hace_tiempo", utils.hace_tiempo)
register.filter("mes_corto", utils.mes_corto)
register.filter("vencimiento_texto", utils.vencimiento_texto)
register.filter("tiempo_restante", utils.tiempo_restante)
register.filter("nota_fmt", utils.nota_fmt)
register.filter("whatsapp_url", utils.whatsapp_url)


@register.filter
def plural(n, palabras):
    """{{ n|plural:"módulo,módulos" }} → «1 módulo» / «3 módulos»"""
    uno, varios = palabras.split(",")
    return utils.plural(int(n), uno, varios)


@register.filter
def primera_palabra(texto):
    """«Quispe Mamani» → «Quispe»"""
    partes = (texto or "").split()
    return partes[0] if partes else ""


@register.filter
def get_item(diccionario, clave):
    """{{ diccionario|get_item:clave }}"""
    return diccionario.get(clave, "") if hasattr(diccionario, "get") else ""
