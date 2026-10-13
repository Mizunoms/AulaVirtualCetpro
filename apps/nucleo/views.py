"""Inicio, tema claro/oscuro, logo y fotos, ajustes del aula y registro de actividad."""

import re
from math import ceil

from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import ajustes, archivos, color
from .models import Registro
from .permisos import exigir, no_encontrado, prohibido
from .utils import error, ok, pagina_error, vista

# ---------- Inicio ----------


@exigir()
def inicio(request):
    # Las pantallas de inicio de cada rol (con sus módulos, tareas y avisos) llegan en la fase 2.
    return vista(request, "nucleo/inicio.html", titulo="Inicio", sub=request.user.get_rol_display(), menu="inicio")


# ---------- Tema claro / oscuro ----------


@require_POST
def tema(request):
    """Cambia entre modo claro y oscuro. Funciona también antes de entrar (pantalla de ingreso)."""
    from apps.cuentas.views import guardar_tema

    volver = request.POST.get("volver", "").strip()
    # Solo se vuelve a una página del aula (nunca a otro sitio ni a una dirección rara).
    prefijo = reverse("nucleo:inicio").rstrip("/")
    destino = volver if re.fullmatch(r"/(?!/)[A-Za-z0-9_\-./?=&%#]*", volver) and "/tema" not in volver else prefijo + "/"
    respuesta = redirect(destino)
    guardar_tema(respuesta, request.POST.get("tema", "").strip())
    return respuesta


# ---------- Logo y fotos (públicos: se ven antes de entrar) ----------


def _imagen_de_ajuste(clave, nombre):
    ruta = ajustes.ajuste(clave)
    if not ruta or not archivos.es_imagen(ruta):
        raise Http404
    ext = ruta.rsplit(".", 1)[-1]
    return archivos.enviar(ruta, f"{nombre}.{ext}", en_linea=True)


def marca_logo(request):
    return _imagen_de_ajuste("logo", "logo")


def marca_fondo(request):
    return _imagen_de_ajuste("fondo_login", "fondo")


def marca_especialidad(request):
    """Foto del taller de una especialidad (?n=Nombre)."""
    nombre = request.GET.get("n", "")
    for esp in ajustes.especialidades():
        if esp["nombre"] == nombre and esp.get("foto") and archivos.es_imagen(esp["foto"]):
            return archivos.enviar(esp["foto"], "especialidad." + esp["foto"].rsplit(".", 1)[-1], en_linea=True)
    raise Http404


# ---------- Ajustes del aula (administrador) ----------

PESTANAS = {
    "identidad": "Identidad visual",
    "periodo": "Periodo y matrículas",
    "contacto": "Contacto y soporte",
}
IMAGENES = {"logo": "Logo", "fondo_login": "Foto de la pantalla de entrada"}


@exigir("admin")
def ajustes_ver(request):
    tab = request.GET.get("tab", "")
    tab = tab if tab in PESTANAS else "identidad"
    a = ajustes.todas()
    valores = {**a, **{k: v for k, v in request.session.get("_old", {}).items() if k in a}}
    return vista(
        request,
        "nucleo/ajustes.html",
        {"a": a, "v": valores, "tab": tab, "pestanas": PESTANAS, "especialidades": ajustes.especialidades()},
        titulo="Ajustes del aula",
        sub=PESTANAS[tab],
        menu="ajustes",
    )


def _error_ajustes(request, volver, mensaje):
    request.session["_old"] = {k: v for k, v in request.POST.items() if k != "csrfmiddlewaretoken"}
    error(request, mensaje)
    return redirect(volver)


@require_POST
@exigir("admin")
def ajustes_guardar(request):
    """Guarda una pestaña de ajustes (identidad, periodo o contacto)."""
    yo = request.user
    tab = request.POST.get("tab", "")
    tab = tab if tab in PESTANAS else "todo"
    volver = reverse("nucleo:ajustes") + ("" if tab == "todo" else f"?tab={tab}")

    if "restaurar_colores" in request.POST:
        ajustes.guardar({k: ajustes.DEFECTO[k] for k in ("color_principal", "color_acento", "color_secundario")})
        Registro.anotar(yo, "ajustes", f"{yo.nombre_completo} volvió a poner los colores del CETPRO.", request)
        ok(request, "Se volvieron a poner los colores del CETPRO.")
        return redirect(reverse("nucleo:ajustes") + "?tab=identidad")

    def texto(clave, maximo):
        return request.POST.get(clave, "").strip()[:maximo]

    d = {}
    if tab in ("identidad", "todo"):
        d.update(
            centro_nombre=texto("centro_nombre", 60), aula_nombre=texto("aula_nombre", 60), bienvenida=texto("bienvenida", 200)
        )
        if not d["centro_nombre"] or not d["aula_nombre"]:
            return _error_ajustes(request, volver, "Escribe el nombre del centro y el nombre del aula.")
        nombres_color = {"color_principal": "principal", "color_acento": "de acento", "color_secundario": "de botones y enlaces"}
        for clave, nombre in nombres_color.items():
            c = request.POST.get(clave, "").strip().upper()
            if not color.valido(c):
                return _error_ajustes(request, volver, f"El color {nombre} no es válido.")
            # Sobre estos colores va letra blanca: deben tener buen contraste (WCAG AA, 4.5 a 1).
            if color.contraste(c, "#FFFFFF") < 4.5:
                return _error_ajustes(
                    request, volver, f"El color {nombre} es muy claro: la letra blanca no se leería bien. Elige uno más oscuro."
                )
            d[clave] = c
    if tab in ("periodo", "todo"):
        d.update(
            aviso_general=texto("aviso_general", 300),
            periodo=texto("periodo", 20),
            dominio_correo=texto("dominio_correo", 60).lstrip("@").lower(),
            registro_abierto="1" if "registro_abierto" in request.POST else "0",
        )
        if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", d["dominio_correo"]):
            return _error_ajustes(request, volver, "Escribe el dominio del correo de los docentes, por ejemplo: cetpro.com")
    if tab in ("contacto", "todo"):
        d.update(
            whatsapp=re.sub(r"\D", "", request.POST.get("whatsapp", ""))[:15],
            telefono=re.sub(r"[^\d +-]", "", request.POST.get("telefono", ""))[:20],
            horario_atencion=texto("horario_atencion", 120),
            web=texto("web", 200),
            reglamento_url=texto("reglamento_url", 300),
            horario_url=texto("horario_url", 300),
        )
        if d["web"] and not re.match(r"https?://", d["web"], re.I):
            return _error_ajustes(request, volver, "La página web debe empezar con https://")
        for clave, nombre in (("reglamento_url", "del reglamento"), ("horario_url", "del horario")):
            if d[clave] and not re.match(r"https?://", d[clave], re.I):
                return _error_ajustes(request, volver, f"El enlace {nombre} debe empezar con https://")
    ajustes.guardar(d)
    cual = "todos" if tab == "todo" else PESTANAS[tab].lower()
    Registro.anotar(yo, "ajustes", f"{yo.nombre_completo} cambió los ajustes del aula ({cual}).", request)
    ok(request, "Ajustes guardados.")
    return redirect(volver)


@require_POST
@exigir("admin")
def ajustes_imagen(request):
    """Subir o quitar el logo o la foto de la pantalla de entrada."""
    cual = request.POST.get("cual", "")
    if cual not in IMAGENES:
        return no_encontrado(request)
    volver = reverse("nucleo:ajustes") + "?tab=identidad#imagenes"
    anterior = ajustes.ajuste(cual)
    if "quitar" in request.POST:
        ajustes.guardar({cual: ""})
        archivos.borrar(anterior)
        ok(request, f"{IMAGENES[cual]}: se volvió a usar el original.")
        return redirect(volver)
    try:
        ruta, _nombre = archivos.guardar(request.FILES.get("imagen"))
    except archivos.ArchivoError as ex:
        error(request, str(ex))
        return redirect(volver)
    if not archivos.es_imagen(ruta):
        archivos.borrar(ruta)
        error(request, "Sube una imagen JPG, PNG o WEBP.")
        return redirect(volver)
    ajustes.guardar({cual: ruta})
    archivos.borrar(anterior)
    ok(request, f"{IMAGENES[cual]} actualizado.")
    return redirect(volver)


@require_POST
@exigir("admin")
def ajustes_foto(request):
    """Foto del taller de una especialidad (se ve en las tarjetas de sus módulos)."""
    nombre = request.POST.get("nombre", "").strip()
    lista = ajustes.especialidades()
    indice = next((i for i, e in enumerate(lista) if e["nombre"] == nombre), None)
    if indice is None:
        return no_encontrado(request)
    volver = reverse("nucleo:ajustes") + "?tab=identidad#fotos"
    anterior = lista[indice].get("foto")
    if "quitar" in request.POST:
        lista[indice].pop("foto", None)
    else:
        try:
            ruta, _n = archivos.guardar(request.FILES.get("foto"))
        except archivos.ArchivoError as ex:
            error(request, str(ex))
            return redirect(volver)
        if not archivos.es_imagen(ruta):
            archivos.borrar(ruta)
            error(request, "Sube una foto JPG, PNG o WEBP.")
            return redirect(volver)
        lista[indice]["foto"] = ruta
    ajustes.guardar_especialidades(lista)
    archivos.borrar(anterior)
    ok(request, f"Foto de {nombre}" + (" quitada." if "quitar" in request.POST else " guardada."))
    return redirect(volver)


# ---------- Registro de actividad (administrador) ----------


@exigir("admin")
def registro(request):
    """Quién hizo qué en el aula."""
    accion = request.GET.get("accion", "")
    accion = accion if accion in Registro.ACCIONES else ""
    por = 25
    consulta = Registro.objects.select_related("usuario")
    if accion:
        consulta = consulta.filter(accion=accion)
    total = consulta.count()
    paginas = max(1, ceil(total / por))
    try:
        num = min(max(1, int(request.GET.get("pagina", 1))), paginas)
    except ValueError:
        num = 1
    filas = consulta[(num - 1) * por : num * por]
    return vista(
        request,
        "nucleo/registro.html",
        {
            "filas": filas,
            "accion": accion,
            "acciones": Registro.ACCIONES,
            "total": total,
            "num_pagina": num,
            "paginas": paginas,
            "desde": (num - 1) * por + 1 if total else 0,
            "hasta": min(total, num * por),
            "base": reverse("nucleo:registro"),
        },
        titulo="Registro de actividad",
        sub="Quién hizo qué en el aula",
        volver=reverse("nucleo:inicio"),
        menu="inicio",
    )


# ---------- Páginas de error ----------


def error_403(request, exception=None):
    return prohibido(request)


def error_404(request, exception=None):
    return no_encontrado(request)


def error_500(request):
    return pagina_error(request, "Algo salió mal de nuestro lado. Inténtalo en unos minutos.", 500)


def error_csrf(request, reason=""):
    return pagina_error(request, "La página estuvo abierta mucho tiempo. Vuelve atrás, recarga e inténtalo otra vez.", 403)
