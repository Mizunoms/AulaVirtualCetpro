"""Cursos (programas de estudios): crear, cambiar, eliminar y encontrar uno.

La lista de cursos vive en los Ajustes (nombre, color y foto de cada uno) y cada módulo guarda el nombre de su curso
(`Modulo.especialidad`): por eso, al cambiar un nombre, se cambia también en sus módulos. Las pantallas encuentran un curso por
su «slug» (el nombre sin tildes ni espacios: «Soporte Técnico» → «soporte-tecnico»); sale del nombre y no se guarda.
"""

import re

from django.db import transaction
from django.utils.text import slugify

from apps.nucleo import ajustes, color

from .models import Modulo

COLOR_NUEVO = "#1249A3"  # el que se propone al crear un curso (oscuro: encima va letra blanca)
COLORES_SUGERIDOS = [
    ("#1249A3", "Azul"),
    ("#166534", "Verde"),
    ("#C8231B", "Rojo"),
    ("#7E22CE", "Morado"),
    ("#9A3412", "Terracota"),
    ("#B45309", "Naranja oscuro"),
    ("#0E7490", "Turquesa"),
    ("#55627F", "Gris azulado"),
]
RESERVADOS = {"nuevo"}  # direcciones que ya usa el aula: «admin/cursos/nuevo»


class CursoError(ValueError):
    """Algo que la persona debe corregir. El mensaje ya viene en español simple."""


def slug_de(nombre):
    return slugify(nombre or "")


def lista():
    """Los cursos de la lista, cada uno con su «slug»: [{"nombre", "color", "foto", "slug"}, …]"""
    return [{**e, "slug": slug_de(e["nombre"])} for e in ajustes.especialidades()]


def buscar(slug):
    return next((c for c in lista() if c["slug"] == slug), None)


def limpiar_nombre(texto):
    return re.sub(r"\s+", " ", texto or "").strip()[:100]


def revisar_nombre(texto, excepto=None):
    """Nombre listo para guardar. `excepto` es el slug del curso que se está cambiando (puede conservar su propio nombre)."""
    nombre = limpiar_nombre(texto)
    slug = slug_de(nombre)
    if not nombre or not slug:
        raise CursoError("Escribe el nombre del curso (con letras).")
    if slug in RESERVADOS:
        raise CursoError("Ese nombre no se puede usar. Escribe otro.")
    for c in lista():
        if c["slug"] == slug and c["slug"] != excepto:
            raise CursoError(f"Ya hay un curso llamado «{c['nombre']}».")
    return nombre


def revisar_color(texto):
    c = (texto or "").strip().upper()
    if not color.valido(c):
        raise CursoError("Elige un color para el curso.")
    if color.contraste(c, "#FFFFFF") < 4.5:
        raise CursoError("Ese color es muy claro: la letra blanca no se leería bien. Elige uno más oscuro.")
    return c


def crear(nombre, color_hex, foto=None):
    """Agrega el curso a la lista y lo devuelve (con su «slug»)."""
    nombre = revisar_nombre(nombre)
    c = revisar_color(color_hex)
    curso = {"nombre": nombre, "color": c, **({"foto": foto} if foto else {})}
    ajustes.guardar_especialidades([*ajustes.especialidades(), curso])
    return {**curso, "slug": slug_de(nombre)}


@transaction.atomic
def cambiar(slug, nombre, color_hex):
    """Cambia el nombre y el color de un curso (la foto se conserva). Si cambia el nombre, cambia también en sus módulos.
    Devuelve (curso nuevo, nombre anterior)."""
    actual = buscar(slug)
    if actual is None:
        raise CursoError("No encontré ese curso.")
    nuevo = revisar_nombre(nombre, excepto=slug)
    c = revisar_color(color_hex)
    ajustes.guardar_especialidades(
        [{**e, "nombre": nuevo, "color": c} if e["nombre"] == actual["nombre"] else e for e in ajustes.especialidades()]
    )
    if nuevo != actual["nombre"]:
        Modulo.objects.filter(especialidad=actual["nombre"]).update(especialidad=nuevo)
    return buscar(slug_de(nuevo)), actual["nombre"]


def poner_foto(nombre, ruta):
    """Guarda la ruta de la foto del curso (o la quita si `ruta` viene vacía). Devuelve la ruta anterior, para borrar el archivo."""
    cursos = ajustes.especialidades()
    anterior = None
    for e in cursos:
        if e["nombre"] == nombre:
            anterior = e.get("foto") or None
            if ruta:
                e["foto"] = ruta
            else:
                e.pop("foto", None)
    ajustes.guardar_especialidades(cursos)
    return anterior


def modulos_de(nombre):
    """Todos los módulos del curso, también los archivados."""
    return Modulo.objects.filter(especialidad=nombre)


def por_que_no_se_elimina(curso):
    """Por qué el curso no se puede eliminar todavía (texto para la persona), o None si se puede."""
    n = modulos_de(curso["nombre"]).count()
    if n:
        return f"Tiene {n} {'módulo' if n == 1 else 'módulos'}. Primero elimina esos módulos o cámbialos a otro curso."
    if len(lista()) <= 1:
        return "Debe quedar al menos un curso."
    return None


def eliminar(slug):
    """Quita el curso de la lista (solo si no tiene módulos). Devuelve el curso quitado, para borrar su foto."""
    curso = buscar(slug)
    if curso is None:
        raise CursoError("No encontré ese curso.")
    motivo = por_que_no_se_elimina(curso)
    if motivo:
        raise CursoError(motivo)
    ajustes.guardar_especialidades([e for e in ajustes.especialidades() if e["nombre"] != curso["nombre"]])
    return curso
