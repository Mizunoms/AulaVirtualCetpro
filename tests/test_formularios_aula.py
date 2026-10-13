"""Cómo los formularios aparecen en el resto del aula: clase, pestaña Tareas, inicio, «Por calificar», notas, copia y eliminación."""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.academico import papelera
from apps.academico.models import Clase, Modulo
from apps.evaluacion import calificacion
from apps.formularios.models import Formulario, Intento, Pregunta
from apps.nucleo import archivos, menu

from . import muestras
from .formularios_comun import nuevo_formulario, pregunta, responder, respuestas_correctas

pytestmark = pytest.mark.django_db


# ===================================================================== En la clase


def test_el_alumno_ve_el_formulario_dentro_de_la_clase(cliente_de, rosa, modulo, clase, examen):
    c = cliente_de(rosa)
    html = c.get(reverse("academico:clase", args=[clase.pk])).content.decode()
    assert "Examen de bioseguridad" in html and "Dar el examen" in html and reverse("formularios:ver", args=[examen.pk]) in html
    responder(c, examen, respuestas_correctas(examen))
    html = c.get(reverse("academico:clase", args=[clase.pk])).content.decode()
    assert "Ya respondiste · Tu nota: 20" in html and "Dar el examen" not in html


def test_el_docente_ve_el_formulario_dentro_de_la_clase(cliente_de, docente, rosa, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(publicado=False)
    html = cliente_de(docente).get(reverse("academico:clase", args=[clase.pk])).content.decode()
    assert "Formulario · Examen" in html and "Sin publicar" in html and "0 respondieron" in html
    assert reverse("formularios:nuevo", args=[modulo.pk]) + f"?clase={clase.pk}" in html  # el botón «Formulario con preguntas»


def test_un_alumno_no_ve_los_formularios_sin_publicar_en_la_clase(cliente_de, rosa, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(publicado=False)
    assert "Examen de bioseguridad" not in cliente_de(rosa).get(reverse("academico:clase", args=[clase.pk])).content.decode()


# ===================================================================== En la pestaña Tareas


def test_lista_de_formularios_en_la_pestana_tareas(cliente_de, docente, rosa, modulo, clase, examen):
    c = cliente_de(rosa)
    url = reverse("tareas:modulo", args=[modulo.pk])
    html = c.get(url).content.decode()
    assert "Examen · " in html and "4 preguntas" in html and "Por responder" in html and "respondieron" not in html
    responder(c, examen, respuestas_correctas(examen))
    assert "Nota 20" in c.get(url).content.decode()
    docente_html = cliente_de(docente).get(url).content.decode()
    assert "1 de 1 respondieron" in docente_html and "Publicado" in docente_html
    Formulario.objects.filter(pk=examen.pk).update(publicado=False)
    assert "Borrador" in cliente_de(docente).get(url).content.decode()
    assert "Examen de bioseguridad" not in c.get(url).content.decode()


def test_la_pestana_tareas_cuenta_lo_que_falta_revisar(cliente_de, docente, rosa, modulo, clase):
    f = nuevo_formulario(clase)
    p = pregunta(f, "abierta", "Explica", puntos=10)
    c = cliente_de(rosa)
    responder(c, f, {f"txt[{p.pk}]": "algo"})
    assert "1 por revisar" in cliente_de(docente).get(reverse("tareas:modulo", args=[modulo.pk])).content.decode()
    assert "Por revisar" in c.get(reverse("tareas:modulo", args=[modulo.pk])).content.decode()


def test_estados_de_los_formularios_que_ya_vencieron_o_no_abren(cliente_de, rosa, modulo, clase, examen):
    url = reverse("tareas:modulo", args=[modulo.pk])
    Formulario.objects.filter(pk=examen.pk).update(fecha_limite=timezone.now() - timedelta(days=1))
    assert "No respondiste" in cliente_de(rosa).get(url).content.decode()
    Formulario.objects.filter(pk=examen.pk).update(
        fecha_limite=timezone.now() + timedelta(days=3), fecha_inicio=timezone.now() + timedelta(days=1)
    )
    assert "Todavía no abre" in cliente_de(rosa).get(url).content.decode()


# ===================================================================== En el inicio


def test_inicio_del_alumno_con_un_formulario_pendiente(cliente_de, rosa, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(tiempo_minutos=20)
    c = cliente_de(rosa)
    html = c.get(reverse("nucleo:inicio")).content.decode()
    assert "Examen de bioseguridad" in html and "Dar el examen" in html and "Examen · 20 min" in html
    assert reverse("formularios:ver", args=[examen.pk]) + "?desde=inicio" in html
    assert menu.contar("inicio", rosa) == 1
    responder(c, examen, respuestas_correctas(examen))
    assert menu.contar("inicio", rosa) == 0 and "Dar el examen" not in c.get(reverse("nucleo:inicio")).content.decode()


def test_el_inicio_del_alumno_solo_cuenta_lo_que_puede_responder(rosa, modulo, clase, examen):
    cambios = (
        {"publicado": False},
        {"fecha_limite": timezone.now() - timedelta(hours=1)},
        {"fecha_inicio": timezone.now() + timedelta(days=1)},
    )
    for cambio in cambios:
        Formulario.objects.filter(pk=examen.pk).update(
            publicado=True, fecha_inicio=None, fecha_limite=timezone.now() + timedelta(days=2)
        )
        Formulario.objects.filter(pk=examen.pk).update(**cambio)
        assert menu.contar("inicio", rosa) == 0, cambio


def test_inicio_del_docente_con_formularios(cliente_de, docente, rosa, modulo, clase, examen):
    f = nuevo_formulario(clase, titulo="Trabajo de la semana", modo="trabajo")
    pregunta(f, "abierta", "Cuenta lo que hiciste", puntos=0, obligatoria=False)
    responder(cliente_de(rosa), f, {})
    assert menu.contar("calificar", docente) == 1
    html = cliente_de(docente).get(reverse("nucleo:inicio")).content.decode()
    assert "Trabajo: Trabajo de la semana" in html and "1 respondió" in html
    assert "Examen: Examen de bioseguridad" in html and "0 respondieron" in html
    assert reverse("formularios:intento", args=[Intento.objects.get().pk]) in html  # un solo trabajo esperando: el botón lo abre


def test_por_calificar_incluye_los_formularios_por_revisar(cliente_de, docente, rosa, modulo, clase):
    f = nuevo_formulario(clase, titulo="Trabajo de la semana", modo="trabajo")
    pregunta(f, "abierta", "Cuenta lo que hiciste", puntos=0, obligatoria=False)
    responder(cliente_de(rosa), f, {})
    html = cliente_de(docente).get(reverse("tareas:por_calificar")).content.decode()
    assert (
        "Trabajo de la semana" in html
        and "Trabajo por revisar" in html
        and "Pendientes (1)" in html
        and "Abrir y revisar" in html
    )
    assert "Rosa Quispe Mamani" in html


# ===================================================================== En las notas


def test_libro_de_notas_con_formularios(rosa, luis, modulo, clase, examen, cliente_de):
    responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    nuevo_formulario(clase, titulo="Sin publicar", publicado=False)
    nuevo_formulario(clase, titulo="Encuesta", modo="encuesta")
    libro = calificacion.libro(modulo)
    assert [a["clave"] for a in libro["actividades"]] == [f"q{examen.pk}"]  # no entran borradores ni encuestas
    alumnos = {a.nombres: a for a in libro["alumnos"]}
    assert alumnos["Rosa"].notas == {f"q{examen.pk}": 20.0} and alumnos["Rosa"].partes["tests"] == 20.0
    assert alumnos["Luis"].notas == {f"q{examen.pk}": "—"}  # todavía puede darlo
    Formulario.objects.filter(pk=examen.pk).update(fecha_limite=timezone.now() - timedelta(days=1))
    alumnos = {a.nombres: a for a in calificacion.libro(modulo)["alumnos"]}
    assert alumnos["Luis"].notas == {f"q{examen.pk}": 0.0}  # ya venció y no lo dio: cuenta como 0


def test_libro_de_notas_cuando_falta_revisar_y_con_varios_intentos(rosa, modulo, clase, cliente_de):
    f = nuevo_formulario(clase, intentos_max=2)
    p = pregunta(f, "abierta", "Explica", puntos=10)
    q = pregunta(f, "opcion", "Elige", [("Uno", True), ("Dos", False)], puntos=10)
    c = cliente_de(rosa)
    i, _ = responder(c, f, {f"txt[{p.pk}]": "algo", f"op[{q.pk}]": q.todas_las_opciones.get(correcta=True).pk})
    alumno = {a.nombres: a for a in calificacion.libro(modulo)["alumnos"]}["Rosa"]
    assert alumno.notas == {f"q{f.pk}": "Por revisar"}
    Intento.objects.filter(pk=i.pk).update(nota=Decimal("12"), revisado=True)
    j, _ = responder(c, f, {f"txt[{p.pk}]": "otra", f"op[{q.pk}]": q.todas_las_opciones.get(correcta=False).pk})
    Intento.objects.filter(pk=j.pk).update(nota=Decimal("8"), revisado=True)
    alumno = {a.nombres: a for a in calificacion.libro(modulo)["alumnos"]}["Rosa"]
    assert alumno.notas == {f"q{f.pk}": 12.0}  # vale la mejor nota


def test_mis_notas_con_un_examen(cliente_de, rosa, modulo, clase, examen):
    c = cliente_de(rosa)
    responder(c, examen, respuestas_correctas(examen))
    html = c.get(reverse("evaluacion:mis_notas")).content.decode()
    assert "Examen de bioseguridad" in html and "20" in html


# ===================================================================== Copiar, eliminar y papelera


def test_copiar_el_modulo_copia_los_formularios(cliente_de, docente, rosa, modulo, clase, examen):
    ruta, _nombre = archivos.guardar(muestras.png())
    primera = examen.preguntas.order_by("orden").first()
    primera.imagen_ruta = ruta
    primera.save()
    Formulario.objects.filter(pk=examen.pk).update(mezclar=True, tiempo_minutos=15, mensaje_final="¡Listo!")
    responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    cliente_de(docente).post(reverse("academico:copiar", args=[modulo.pk]), {"nombre": "Copia 2027", "periodo": "2027-I"})
    nuevo = Modulo.objects.exclude(pk=modulo.pk).get()
    copia = Formulario.objects.get(clase__modulo=nuevo)
    assert (copia.titulo, copia.modo, copia.mezclar, copia.tiempo_minutos, copia.mensaje_final, copia.publicado) == (
        "Examen de bioseguridad", "examen", True, 15, "¡Listo!", True,
    )  # fmt: skip
    assert not copia.intentos.exists()  # sin respuestas
    nuevas, viejas = copia.preguntas_completas(), examen.preguntas_completas()
    assert [(p.tipo, p.enunciado, p.puntos) for p in nuevas] == [(p.tipo, p.enunciado, p.puntos) for p in viejas]
    assert [[(o.texto, o.correcta) for o in p.opciones] for p in nuevas] == [
        [(o.texto, o.correcta) for o in p.opciones] for p in viejas
    ]
    assert (
        nuevas[0].imagen_ruta and nuevas[0].imagen_ruta != ruta and (Path(settings.MEDIA_ROOT) / nuevas[0].imagen_ruta).is_file()
    )
    assert nuevas[3].respuestas_aceptadas == "degrafilado\ndegradado"
    assert Formulario.objects.filter(clase__modulo=modulo).count() == 1  # el original sigue igual


def test_el_resumen_al_eliminar_el_modulo_cuenta_los_formularios(cliente_de, admin, rosa, modulo, clase, examen):
    responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    assert modulo.tiene_registros_de_alumnos()
    html = cliente_de(admin).get(reverse("academico:admin_eliminar", args=[modulo.pk])).content.decode()
    assert "1 formulario" in html and "1 test rendido" in html
    cliente_de(admin).post(reverse("academico:admin_eliminar", args=[modulo.pk]), {"entiendo": "1"})
    assert not Modulo.objects.exists() and not Formulario.todos.exists()
    assert not Pregunta.objects.exists() and not Intento.objects.exists()


def test_el_docente_no_elimina_un_modulo_con_tests_rendidos(cliente_de, docente, rosa, modulo, clase, examen):
    responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    c = cliente_de(docente)
    r = c.post(reverse("academico:eliminar", args=[modulo.pk]), {"entiendo": "1"})
    assert "ya tiene trabajos, tests o asistencia" in c.get(r["Location"]).content.decode()
    assert Modulo.objects.exists()


def test_una_clase_con_formularios_no_se_borra(cliente_de, docente, modulo, clase, examen):
    c = cliente_de(docente)
    r = c.post(reverse("academico:eliminar_clase", args=[clase.pk]))
    assert "Primero borra los materiales, tareas y formularios" in c.get(r["Location"]).content.decode()
    assert Clase.objects.filter(pk=clase.pk).exists()


def test_la_papelera_borra_de_verdad_a_los_30_dias(modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(eliminado=timezone.now() - timedelta(days=31))
    reciente = nuevo_formulario(clase, titulo="Reciente")
    Formulario.objects.filter(pk=reciente.pk).update(eliminado=timezone.now() - timedelta(days=5))
    assert papelera.vaciar_viejos() == 1
    assert [f.titulo for f in Formulario.todos.all()] == ["Reciente"]
    assert not Pregunta.objects.filter(formulario_id=examen.pk).exists()
