"""Importar preguntas al formulario: pegar texto (por ejemplo, de una IA) o subir Excel / CSV / Word. Primero se revisa, luego se agrega."""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.cuentas.models import Rol
from apps.nucleo import importador
from apps.nucleo.permisos import exigir
from apps.nucleo.utils import error, plural, por_metodo, vista

from .models import TIPOS, Pregunta
from .views import _editable

MAX_TEXTO = 100_000


def _instruccion_para_la_ia(modulo):
    return (
        f"Hazme 10 preguntas sobre [ESCRIBE AQUÍ EL TEMA] para alumnos de {modulo.nombre} de un CETPRO (personas adultas). "
        "Usa palabras sencillas. Escríbelas EXACTAMENTE con este formato, sin tablas ni negritas:\n\n"
        "1. Texto de la pregunta\na) opción\nb) opción\nc) opción\nd) opción\nRespuesta: b\nPuntos: 2\n\n"
        "Reglas: numera las preguntas (1., 2., 3.…). Para verdadero o falso usa «a) Verdadero» y «b) Falso». "
        "Si una pregunta tiene varias respuestas correctas, escribe «Respuesta: a, c». "
        "Para una pregunta de escribir, no pongas opciones y escribe la respuesta corta después de «Respuesta:»."
    )


def _pantalla(request, f, modulo, resultado, texto, titulo, volver):
    if resultado is not None:  # lo que se muestra para revisar (no es lo que se guarda)
        num = 0
        for p in resultado["preguntas"]:
            p["numero"] = None if p["tipo"] == "seccion" else (num := num + 1)
            p["tipo_nombre"] = TIPOS[p["tipo"]][0]
            p["aceptadas_texto"] = " · ".join((p["aceptadas"] or "").splitlines())
    return vista(
        request,
        "formularios/importar.html",
        {
            "q": f,
            "modulo": modulo,
            "resultado": resultado,
            "texto": texto,
            "es_examen": f.es_examen,
            "instruccion": _instruccion_para_la_ia(modulo),
            "cantidad": plural(len(resultado["preguntas"]), "pregunta", "preguntas") if resultado else "",
            "errores_titulo": (
                "Hay 1 pregunta que no pudimos leer"
                if resultado and len(resultado["errores"]) == 1
                else f"Hay {len(resultado['errores'])} preguntas que no pudimos leer"
            )
            if resultado
            else "",
        },
        titulo=titulo,
        sub=f.titulo,
        volver=volver,
        menu="cursos",
    )


@exigir(Rol.DOCENTE)
def importar(request, id):
    f, modulo = _editable(request, id)
    return _pantalla(request, f, modulo, None, "", "Importar preguntas", reverse("formularios:ver", args=[id]))


@require_POST
@exigir(Rol.DOCENTE)
def procesar(request, id):
    """Lee el texto o el archivo y muestra la vista previa (todavía no guarda nada)."""
    f, modulo = _editable(request, id)
    texto = (request.POST.get("texto") or "")[:MAX_TEXTO]
    subido = request.FILES.get("archivo")
    try:
        if subido is not None and subido.size > 0:
            if subido.size > settings.ARCHIVOS_MAX_MB * 1024 * 1024:
                raise importador.ImportadorError(
                    f"No se pudo leer el archivo. Revisa que pese menos de {settings.ARCHIVOS_MAX_MB} MB."
                )
            resultado = importador.desde_archivo(subido, subido.name, f.es_examen)
        elif texto.strip():
            resultado = importador.desde_texto(texto, f.es_examen)
        else:
            raise importador.ImportadorError("Pega el texto con las preguntas o elige un archivo.")
    except importador.ImportadorError as ex:
        messages.error(request, str(ex))
        return _pantalla(request, f, modulo, None, texto, "Importar preguntas", reverse("formularios:ver", args=[id]))
    request.session["_importacion"] = {"formulario": id, "preguntas": resultado["preguntas"]}
    return _pantalla(request, f, modulo, resultado, texto, "Revisa antes de agregar", reverse("formularios:importar", args=[id]))


@require_POST
@exigir(Rol.DOCENTE)
def confirmar(request, id):
    """Agrega al formulario las preguntas que el docente revisó."""
    f, _modulo = _editable(request, id)
    guardado = request.session.pop("_importacion", None)
    if not isinstance(guardado, dict) or guardado.get("formulario") != id or not guardado.get("preguntas"):
        error(request, "No hay preguntas para agregar. Vuelve a pegar el texto o subir el archivo.")
        return redirect("formularios:importar", id=id)
    for p in guardado["preguntas"]:
        Pregunta.guardar(f, None, p)
    n = len(guardado["preguntas"])
    messages.success(request, plural(n, "pregunta agregada", "preguntas agregadas") + ". Revísalas y cambia lo que haga falta.")
    return redirect("formularios:ver", id=id)


importar_o_procesar = por_metodo(GET=importar, POST=procesar)
