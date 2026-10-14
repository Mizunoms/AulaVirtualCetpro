"""Inicio, tema claro/oscuro, logo y fotos, ajustes del aula y registro de actividad."""

import re
from math import ceil

from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import ajustes, archivos, ayuda, color
from .models import Notificacion, Registro
from .permisos import exigir, no_encontrado, prohibido
from .utils import error, ok, pagina_error, vista, volver_con_error

# ---------- Inicio ----------


@exigir()
def inicio(request):
    """Pantalla de inicio de cada rol (alumno, docente, administración o dirección)."""
    from apps.academico.views_inicio import inicio as inicio_de_rol

    plantilla, datos = inicio_de_rol(request)
    datos["ayuda_pie"] = True  # al final del Inicio: «¿Necesitas ayuda?»
    # Tutorial: se abre solo la primera vez que la persona entra, o cuando toca «Repetir tutorial» (/?tutorial=1)
    repetir = request.GET.get("tutorial") == "1"
    if repetir or request.user.tutorial_visto is None:
        datos["tutorial"] = {"pasos": ayuda.pasos_de(request.user.rol), "repetido": repetir}
    return vista(request, plantilla, datos, titulo="Inicio", menu="inicio")


@exigir()
def ayuda_ver(request):
    """«Ayuda»: resumen del sistema para el rol de la persona, preguntas frecuentes y el botón «Repetir tutorial»."""
    datos = ayuda.resumen_de(request.user.rol)
    return vista(request, "nucleo/ayuda.html", datos, titulo="Ayuda", sub="Qué es y cómo se usa", menu="cuenta")


@require_POST
@exigir()
def tutorial_visto(request):
    """La persona terminó o saltó el tutorial: ya no se le abre solo (puede repetirlo cuando quiera)."""
    u = request.user
    u.tutorial_visto = timezone.now()
    u.save(update_fields=["tutorial_visto"])
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse({"ok": True})
    return redirect("nucleo:inicio")


@exigir()
def avisos(request):
    """La campana: avisos nuevos y, para el alumno, lo que vence pronto."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.academico import contenido

    u = request.user
    pronto = []
    if u.rol == "alumno":
        ahora = timezone.now()
        limite = ahora + timedelta(hours=36)
        pendientes, _grupos = contenido.pendientes_agrupados(u)
        pronto = [p for p in pendientes if p.limite and ahora <= p.limite <= limite]
    lista = list(Notificacion.objects.filter(usuario=u)[:40])
    Notificacion.marcar_leidas(u)
    return vista(
        request, "nucleo/avisos.html", {"avisos": lista, "pronto": pronto}, titulo="Avisos", sub="Lo nuevo para ti", menu="avisos"
    )


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
    "especialidades": "Cursos",
}
IMAGENES = {"logo": "Logo", "fondo_login": "Foto de la pantalla de entrada"}


@exigir("admin")
def ajustes_ver(request):
    from apps.academico.models import Modulo

    tab = request.GET.get("tab", "")
    tab = tab if tab in PESTANAS else "identidad"
    a = ajustes.todas()
    old = request.session.get("_old", {})
    valores = {**a, **{k: v for k, v in old.items() if k in a}}
    en_uso = Modulo.contar_por_especialidad()
    filas = [dict(e, usa=en_uso.get(e["nombre"], 0)) for e in ajustes.especialidades()]
    filas += [{"nombre": "", "color": "#1249A3", "usa": 0}, {"nombre": "", "color": "#166534", "usa": 0}]
    return vista(
        request,
        "nucleo/ajustes.html",
        {
            "a": a,
            "v": valores,
            "tab": tab,
            "pestanas": PESTANAS,
            "especialidades": ajustes.especialidades(),
            "filas_especialidades": filas,
            "conteos_modulos": Modulo.conteos_admin(),
        },
        titulo="Ajustes del aula",
        sub=PESTANAS[tab],
        menu="ajustes",
    )


def _error_ajustes(request, volver, mensaje):
    return volver_con_error(request, volver, mensaje)


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


@require_POST
@exigir("admin")
def ajustes_especialidades(request):
    """Agregar, renombrar, cambiar color o quitar cursos (especialidades)."""
    from apps.academico.models import Modulo

    volver = reverse("nucleo:ajustes") + "?tab=especialidades"
    # Los campos llegan como nombre[0], nombre[1]… (igual que en el sistema anterior)
    indices = sorted({int(m.group(1)) for k in request.POST for m in [re.fullmatch(r"nombre\[(\d+)\]", k)] if m})
    en_uso = Modulo.contar_por_especialidad()
    fotos = {e["nombre"]: e["foto"] for e in ajustes.especialidades() if e.get("foto")}  # se conservan al renombrar
    lista, renombrar = [], {}
    for i in indices:
        nombre = request.POST.get(f"nombre[{i}]", "").strip()[:100]
        original = request.POST.get(f"original[{i}]", "").strip()
        c = request.POST.get(f"color[{i}]", "").strip().upper()
        if f"quitar[{i}]" in request.POST:
            if original and en_uso.get(original, 0) > 0:
                return volver_con_error(
                    request, volver, f"«{original}» tiene módulos: no se puede quitar. Puedes cambiarle el nombre."
                )
            continue
        if not nombre:
            if original:
                return volver_con_error(request, volver, "Escribe el nombre de cada curso (o marca «Quitar»).")
            continue
        if not color.valido(c) or color.contraste(c, "#FFFFFF") < 4.5:
            return volver_con_error(
                request, volver, f"El color de «{nombre}» es muy claro para letra blanca. Elige uno más oscuro."
            )
        if nombre.lower() in (e["nombre"].lower() for e in lista):
            return volver_con_error(request, volver, f"«{nombre}» está repetida.")
        lista.append({"nombre": nombre, "color": c, **({"foto": fotos[original]} if original in fotos else {})})
        if original and original != nombre:
            renombrar[original] = nombre
    if not lista:
        return volver_con_error(request, volver, "Debe quedar al menos un curso.")
    ajustes.guardar_especialidades(lista)
    for de, a in renombrar.items():
        Modulo.objects.filter(especialidad=de).update(especialidad=a)
    ok(request, "Cursos guardados.")
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
