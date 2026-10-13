"""Datos de prueba que comparten las pruebas de formularios: módulo, clase, alumnos, un examen armado y ayudas para responder.
Los fixtures se registran como plugin en tests/conftest.py."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academico.models import Clase, Modulo
from apps.cuentas.models import Rol, Usuario
from apps.formularios.models import Formulario, Intento, Pregunta

from .conftest import CLAVE


@pytest.fixture
def modulo(docente):
    return Modulo.crear(
        nombre="Peluquería – M1", especialidad="Peluquería y Barbería", periodo="2026-II", turno="mañana", docente=docente
    )


@pytest.fixture
def clase(modulo):
    return Clase.crear(modulo, "Corte básico")


@pytest.fixture
def rosa(modulo, alumno):
    modulo.matricular(alumno)
    return alumno


@pytest.fixture
def luis(modulo):
    u = Usuario.objects.create_user(dni="40000001", nombres="Luis", apellidos="Paz", password=CLAVE, rol=Rol.ALUMNO)
    modulo.matricular(u)
    return u


@pytest.fixture
def otro_docente(db):
    return Usuario.objects.create_user(
        correo="pedro@cetpro.com", nombres="Pedro", apellidos="Rojas", password=CLAVE, rol=Rol.DOCENTE
    )


@pytest.fixture
def forastero(db):
    return Usuario.objects.create_user(dni="40000099", nombres="Julia", apellidos="Vega", password=CLAVE, rol=Rol.ALUMNO)


def nuevo_formulario(clase, modo="examen", publicado=True, dias=7, **extra):
    return Formulario.objects.create(
        clase=clase, modo=modo, titulo=extra.pop("titulo", "Examen de bioseguridad"),
        fecha_limite=timezone.now() + timedelta(days=dias), publicado=publicado, **extra
    )  # fmt: skip


def pregunta(f, tipo, enunciado, opciones=(), puntos=2, **extra):
    """Agrega una pregunta. `opciones` = [(texto, correcta), …] (o con grupo para cuadrículas)."""
    d = {
        "tipo": tipo, "enunciado": enunciado, "obligatoria": True, "puntos": puntos,
        "opciones": [(o[0], o[1], o[2] if len(o) > 2 else "opcion") for o in opciones],
    }  # fmt: skip
    d.update(extra)
    return Pregunta.guardar(f, None, d)


@pytest.fixture
def examen(clase):
    """Examen publicado con 4 preguntas de 5 puntos (20 en total): una sola correcta, casillas, verdadero/falso y corta."""
    f = nuevo_formulario(clase)
    pregunta(
        f, "opcion", "¿Qué se usa para desenredar?", [("Navaja", False), ("Peine ancho", True), ("Secadora", False)], puntos=5
    )
    pregunta(
        f, "multiple", "¿Cuáles son de bioseguridad?", [("Guantes", True), ("Mascarilla", True), ("Anillos", False)], puntos=5
    )
    pregunta(f, "vf", "La tijera se desinfecta.", [("Verdadero", True), ("Falso", False)], puntos=5)
    pregunta(f, "corta", "Corte de corto a largo", puntos=5, aceptadas="degrafilado\ndegradado")
    return f


def respuestas_correctas(f):
    """Lo que envía el alumno cuando responde todo bien."""
    datos = {}
    for p in f.preguntas_completas():
        if p.tipo in ("opcion", "vf"):
            datos[f"op[{p.pk}]"] = next(o.pk for o in p.opciones if o.correcta)
        elif p.tipo == "multiple":
            datos[f"op[{p.pk}][]"] = [o.pk for o in p.opciones if o.correcta]
        elif p.tipo == "corta":
            datos[f"txt[{p.pk}]"] = "  DEGRADADO "
    return datos


def responder(c, f, datos):
    """El alumno empieza y envía. Devuelve (intento, respuesta HTTP del envío)."""
    c.post(reverse("formularios:empezar", args=[f.pk]))
    i = Intento.objects.filter(formulario=f).order_by("-id").first()
    return i, c.post(reverse("formularios:intento", args=[i.pk]), datos)


def datos_de_formulario(clase, **cambio):
    base = {
        "modo": "examen", "titulo": "Examen de bioseguridad", "instrucciones": "Responde con calma.",
        "fecha": (timezone.localdate() + timedelta(days=3)).isoformat(), "hora": "18:30", "tiempo_minutos": "0",
        "intentos_max": "1", "unidad_id": clase.pk, "mostrar_respuestas": "1",
    }  # fmt: skip
    base.update(cambio)
    return base
