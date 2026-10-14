"""Un curso (programa de estudios) por dentro: crearlo, ver sus módulos, cambiarlo y eliminarlo (solo el administrador).

De aquí sale todo lo del curso: «Agregar módulo» llega al formulario de módulo con el curso ya elegido.
La lista de cursos está en `views_admin.cursos`; la lógica (nombre, color, foto, cascada al renombrar) en `cursos.py`.
"""

from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.nucleo import archivos
from apps.nucleo.contexto import foto_especialidad
from apps.nucleo.models import Registro
from apps.nucleo.permisos import exigir, no_encontrado
from apps.nucleo.utils import error, ok, por_metodo, vista, volver_con_error

from . import cursos
from .models import Modulo


def _curso_o_404(request, slug):
    curso = cursos.buscar(slug)
    return curso, (None if curso else no_encontrado(request))


# ---------- Ver ----------


@exigir("admin")
def ver(request, slug):
    """El curso con todos sus módulos y lo que se puede hacer desde aquí."""
    curso, falta = _curso_o_404(request, slug)
    if falta:
        return falta
    todos = list(cursos.modulos_de(curso["nombre"]).con_alumnos().order_by("-activo", "nombre"))
    activos = [m for m in todos if m.activo]
    resumen = Modulo.resumen_por_especialidad().get(curso["nombre"], {"modulos": 0, "docentes": 0, "alumnos": 0})
    return vista(
        request,
        "admin/cursos/ver.html",
        {
            "curso": curso,
            "foto": foto_especialidad(curso["nombre"]),
            "modulos": activos,
            "archivados": len(todos) - len(activos),
            "resumen": resumen,
            "motivo_no_eliminar": cursos.por_que_no_se_elimina(curso),
        },
        titulo=curso["nombre"],
        sub="Curso · sus módulos",
        volver=reverse("academico:admin_cursos"),
        menu="admin-cursos",
    )


# ---------- Crear ----------


def _formulario(request, curso):
    """Datos del formulario de curso (nuevo o editar); si volvió con un error, lo que la persona había escrito."""
    old = request.session.get("_old", {})
    return {
        "curso": curso,
        "nuevo": curso is None,
        "v": {
            "nombre": old.get("nombre", curso["nombre"] if curso else ""),
            "color": old.get("color", curso["color"] if curso else cursos.COLOR_NUEVO),
        },
        "colores": cursos.COLORES_SUGERIDOS,
        "foto": foto_especialidad(curso["nombre"]) if curso else None,
    }


@exigir("admin")
def nuevo(request):
    return vista(
        request,
        "admin/cursos/form.html",
        _formulario(request, None),
        titulo="Nuevo curso",
        sub="Primero el curso; después sus módulos",
        volver=reverse("academico:admin_cursos"),
        menu="admin-cursos",
    )


def _guardar_foto(request, volver):
    """Sube la foto si la persona eligió una. Devuelve (ruta o None, redirección con el error o None)."""
    subida = request.FILES.get("foto")
    if subida is None:
        return None, None
    try:
        ruta, _nombre = archivos.guardar(subida)
    except archivos.ArchivoError as ex:
        return None, volver_con_error(request, volver, str(ex))
    if not archivos.es_imagen(ruta):
        archivos.borrar(ruta)
        return None, volver_con_error(request, volver, "Sube una foto JPG, PNG o WEBP.")
    return ruta, None


@require_POST
@exigir("admin")
def crear(request):
    yo = request.user
    volver = reverse("academico:admin_curso_nuevo")
    nombre, color_hex = request.POST.get("nombre", ""), request.POST.get("color", "")
    try:  # se revisa todo antes de subir la foto, para no dejar archivos sueltos
        cursos.revisar_nombre(nombre)
        cursos.revisar_color(color_hex)
    except cursos.CursoError as ex:
        return volver_con_error(request, volver, str(ex))
    ruta, falla = _guardar_foto(request, volver)
    if falla:
        return falla
    try:
        curso = cursos.crear(nombre, color_hex, foto=ruta)
    except cursos.CursoError as ex:
        archivos.borrar(ruta)
        return volver_con_error(request, volver, str(ex))
    Registro.anotar(yo, "ajustes", f"{yo.nombre_completo} creó el curso «{curso['nombre']}».", request)
    ok(request, f"Curso «{curso['nombre']}» creado. Ahora agrega su primer módulo.")
    return redirect("academico:admin_curso", slug=curso["slug"])


# ---------- Cambiar ----------


@exigir("admin")
def editar(request, slug):
    curso, falta = _curso_o_404(request, slug)
    if falta:
        return falta
    return vista(
        request,
        "admin/cursos/form.html",
        _formulario(request, curso),
        titulo="Editar curso",
        sub=curso["nombre"],
        volver=reverse("academico:admin_curso", args=[slug]),
        menu="admin-cursos",
    )


@require_POST
@exigir("admin")
def actualizar(request, slug):
    yo = request.user
    curso, falta = _curso_o_404(request, slug)
    if falta:
        return falta
    volver = reverse("academico:admin_curso_editar", args=[slug])
    nombre, color_hex = request.POST.get("nombre", ""), request.POST.get("color", "")
    try:
        cursos.revisar_nombre(nombre, excepto=slug)
        cursos.revisar_color(color_hex)
    except cursos.CursoError as ex:
        return volver_con_error(request, volver, str(ex))
    ruta, falla = _guardar_foto(request, volver)
    if falla:
        return falla
    try:
        nuevo_curso, nombre_anterior = cursos.cambiar(slug, nombre, color_hex)
    except cursos.CursoError as ex:
        archivos.borrar(ruta)
        return volver_con_error(request, volver, str(ex))
    if ruta or "quitar_foto" in request.POST:  # la foto vieja se borra cuando todo ya quedó guardado
        archivos.borrar(cursos.poner_foto(nuevo_curso["nombre"], ruta))
    detalle = f"{yo.nombre_completo} cambió el curso «{nombre_anterior}»"
    detalle += f" (ahora se llama «{nuevo_curso['nombre']}»)." if nombre_anterior != nuevo_curso["nombre"] else "."
    Registro.anotar(yo, "ajustes", detalle, request)
    ok(request, "Cambios guardados.")
    return redirect("academico:admin_curso", slug=nuevo_curso["slug"])


# ---------- Eliminar (de verdad) ----------


@exigir("admin")
def confirmar_eliminar(request, slug):
    """Pantalla de confirmación: dice qué se pierde, o por qué todavía no se puede eliminar."""
    curso, falta = _curso_o_404(request, slug)
    if falta:
        return falta
    return vista(
        request,
        "admin/cursos/eliminar.html",
        {
            "curso": curso,
            "foto": foto_especialidad(curso["nombre"]),
            "motivo": cursos.por_que_no_se_elimina(curso),
            "modulos": list(cursos.modulos_de(curso["nombre"]).order_by("-activo", "nombre")),
        },
        titulo="Eliminar curso",
        sub="Revisa antes de borrar",
        volver=reverse("academico:admin_curso", args=[slug]),
        menu="admin-cursos",
    )


@require_POST
@exigir("admin")
def eliminar(request, slug):
    """Elimina el curso de verdad (con su foto). Si todavía tiene módulos, no se puede: antes hay que eliminarlos."""
    yo = request.user
    curso, falta = _curso_o_404(request, slug)
    if falta:
        return falta
    try:
        quitado = cursos.eliminar(slug)
    except cursos.CursoError as ex:
        error(request, str(ex))
        return redirect("academico:admin_curso_eliminar", slug=slug)
    archivos.borrar(quitado.get("foto"))
    Registro.anotar(yo, "ajustes", f"{yo.nombre_completo} eliminó el curso «{quitado['nombre']}».", request)
    ok(request, f"Curso eliminado: «{quitado['nombre']}».")
    return redirect("academico:admin_cursos")


nuevo_o_crear = por_metodo(GET=nuevo, POST=crear)
editar_o_actualizar = por_metodo(GET=editar, POST=actualizar)
confirmar_o_eliminar = por_metodo(GET=confirmar_eliminar, POST=eliminar)
