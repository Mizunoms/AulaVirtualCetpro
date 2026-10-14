"""Formularios con nota: el docente los arma, el alumno los responde, se corrigen solos o los revisa el docente."""

import csv
import io
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.academico.models import Clase
from apps.formularios import calificar
from apps.formularios.models import Formulario, Intento, Opcion, Pregunta, Respuesta
from apps.nucleo.models import Notificacion

from . import muestras
from .formularios_comun import datos_de_formulario, nuevo_formulario, pregunta, responder, respuestas_correctas

pytestmark = pytest.mark.django_db


# ===================================================================== Crear el formulario


def test_pantalla_para_crear(cliente_de, docente, modulo, clase):
    html = (
        cliente_de(docente)
        .get(reverse("formularios:nuevo", args=[modulo.pk]) + f"?clase={clase.pk}&modo=trabajo")
        .content.decode()
    )
    assert "Es como un formulario de Google" in html and "1. ¿Qué vas a crear?" in html
    assert 'id="modo-trabajo" value="trabajo" checked' in html and "Clase: Corte básico" in html
    assert (timezone.localdate() + timedelta(days=7)).isoformat() in html and "Siguiente: agregar preguntas" in html


def test_crear_formulario(cliente_de, docente, modulo, clase):
    c = cliente_de(docente)
    r = c.post(
        reverse("formularios:guardar", args=[modulo.pk]),
        datos_de_formulario(clase, tiempo_minutos="45", intentos_max="3", mezclar="1", mensaje_final="¡Gracias!"),
    )
    f = Formulario.objects.get()
    assert r["Location"] == reverse("formularios:ver", args=[f.pk]) + "#nueva"
    assert "Formulario creado. Ahora agrega las preguntas." in c.get(r["Location"]).content.decode()
    assert (f.modo, f.titulo, f.tiempo_minutos, f.intentos_max, f.mezclar, f.mostrar_respuestas, f.publicado) == (
        "examen", "Examen de bioseguridad", 45, 3, True, True, False,
    )  # fmt: skip
    limite = timezone.localtime(f.fecha_limite)
    assert limite.strftime("%H:%M") == "18:30" and f.clase == clase and f.mensaje_final == "¡Gracias!"


def test_crear_sin_clase_elegida_usa_la_ultima(cliente_de, docente, modulo, clase):
    cliente_de(docente).post(reverse("formularios:guardar", args=[modulo.pk]), datos_de_formulario(clase, unidad_id=""))
    assert Formulario.objects.get().clase == clase


def test_valores_corregidos_al_crear(cliente_de, docente, modulo, clase):
    cliente_de(docente).post(
        reverse("formularios:guardar", args=[modulo.pk]), datos_de_formulario(clase, tiempo_minutos="900", intentos_max="40")
    )
    f = Formulario.objects.get()
    assert f.tiempo_minutos == 300 and f.intentos_max == 5


@pytest.mark.parametrize(
    ("cambio", "mensaje"),
    [
        ({"titulo": " "}, "Escribe el nombre del formulario."),
        ({"modo": "otro"}, "Elige si es examen, trabajo o encuesta."),
        ({"fecha": ""}, "Elige hasta qué día se puede responder."),
        ({"fecha": "no es fecha"}, "Elige hasta qué día se puede responder."),
        ({"desde_fecha": "2020-13-45"}, "La fecha «desde» no es válida."),
        ({"desde_fecha": "2099-01-01"}, "La fecha «desde» debe ser antes de la fecha límite."),
    ],
)
def test_datos_incorrectos_al_crear(cliente_de, docente, modulo, clase, cambio, mensaje):
    c = cliente_de(docente)
    r = c.post(reverse("formularios:guardar", args=[modulo.pk]), datos_de_formulario(clase, **cambio))
    assert r["Location"] == reverse("formularios:nuevo", args=[modulo.pk])
    assert mensaje in c.get(r["Location"]).content.decode()
    assert Formulario.objects.count() == 0


def test_al_volver_con_error_conserva_lo_escrito(cliente_de, docente, modulo, clase):
    c = cliente_de(docente)
    r = c.post(
        reverse("formularios:guardar", args=[modulo.pk]),
        datos_de_formulario(clase, titulo="", instrucciones="Mis indicaciones", intentos_max="2"),
    )
    html = c.get(r["Location"]).content.decode()
    assert "Mis indicaciones" in html and '<option value="2" selected>' in html


def test_solo_el_docente_del_modulo_crea_formularios(cliente_de, alumno, rosa, otro_docente, admin, modulo, clase):
    for quien in (rosa, otro_docente, admin):
        c = cliente_de(quien)
        assert c.get(reverse("formularios:nuevo", args=[modulo.pk])).status_code == 403
        assert c.post(reverse("formularios:guardar", args=[modulo.pk]), datos_de_formulario(clase)).status_code == 403
    assert Formulario.objects.count() == 0


def test_cambiar_los_datos_del_formulario(cliente_de, docente, modulo, clase):
    f = nuevo_formulario(clase, publicado=False)
    c = cliente_de(docente)
    html = c.get(reverse("formularios:editar", args=[f.pk])).content.decode()
    assert "Datos del formulario" in html and "Guardar cambios" in html and 'value="Examen de bioseguridad"' in html
    r = c.post(
        reverse("formularios:editar", args=[f.pk]),
        datos_de_formulario(clase, titulo="Examen final", modo="trabajo", intentos_max="2"),
    )
    assert r["Location"] == reverse("formularios:ver", args=[f.pk])
    f.refresh_from_db()
    assert (f.titulo, f.modo, f.intentos_max) == ("Examen final", "trabajo", 2)
    assert f.mezclar is False  # no se marcó


def test_no_se_cambia_el_tipo_si_ya_hay_respuestas(cliente_de, docente, rosa, modulo, clase, examen):
    Intento.objects.create(formulario=examen, alumno=rosa, fin=timezone.now(), revisado=True)
    c = cliente_de(docente)
    r = c.post(reverse("formularios:editar", args=[examen.pk]), datos_de_formulario(clase, modo="encuesta"))
    assert "Ya hay respuestas: no se puede cambiar si es examen, trabajo o encuesta." in c.get(r["Location"]).content.decode()
    examen.refresh_from_db()
    assert examen.modo == "examen"
    # lo demás sí se puede cambiar
    c.post(reverse("formularios:editar", args=[examen.pk]), datos_de_formulario(clase, titulo="Nuevo nombre"))
    examen.refresh_from_db()
    assert examen.titulo == "Nuevo nombre"


# ===================================================================== Armar las preguntas


def agregar(c, f, **datos):
    return c.post(reverse("formularios:agregar_pregunta", args=[f.pk]), datos)


def test_editor_de_un_formulario_vacio(cliente_de, docente, modulo, clase):
    f = nuevo_formulario(clase, publicado=False)
    html = cliente_de(docente).get(reverse("formularios:ver", args=[f.pk])).content.decode()
    assert "Borrador: tus alumnos todavía no lo ven" in html and "0 preguntas" in html and "Todavía no hay preguntas" in html
    assert "Agregar pregunta 1" in html and "Importar preguntas" in html and "Publicar para mis alumnos" in html
    assert "Borrar este formulario" in html and "La nota va de 0 a 20 según los puntos." in html


def test_agregar_pregunta_de_opciones(cliente_de, docente, modulo, clase):
    f = nuevo_formulario(clase, publicado=False)
    c = cliente_de(docente)
    r = agregar(
        c, f, tipo="opcion", enunciado="¿Qué se usa para desenredar?", puntos="2,5", obligatoria="1", explicacion="El ancho no rompe",
        **{"opcion[0]": "Navaja", "opcion[1]": "Peine ancho", "opcion[2]": "", "opcion[3]": "Secadora", "correctas[]": "1"},
    )  # fmt: skip
    p = Pregunta.objects.get()
    assert r["Location"] == reverse("formularios:ver", args=[f.pk]) + f"#p{p.pk}"
    assert "Pregunta agregada. Para otra, toca «+ Agregar pregunta»." in c.get(r["Location"]).content.decode()
    assert (p.tipo, p.puntos, p.obligatoria, p.orden, p.explicacion) == ("opcion", Decimal("2.5"), True, 1, "El ancho no rompe")
    assert [(o.texto, o.correcta) for o in p.todas_las_opciones.all()] == [
        ("Navaja", False),
        ("Peine ancho", True),
        ("Secadora", False),
    ]


def test_las_preguntas_se_numeran_y_van_al_final(cliente_de, docente, modulo, clase):
    f = nuevo_formulario(clase, publicado=False)
    c = cliente_de(docente)
    for n in range(3):
        agregar(c, f, tipo="abierta", enunciado=f"Pregunta {n}", puntos="1", obligatoria="1")
    assert list(Pregunta.objects.values_list("orden", flat=True)) == [1, 2, 3]
    assert "Agregar pregunta 4" in c.get(reverse("formularios:ver", args=[f.pk])).content.decode()


@pytest.mark.parametrize(
    ("datos", "mensaje"),
    [
        ({"tipo": "raro", "enunciado": "x"}, "Elige el tipo de pregunta."),
        ({"tipo": "abierta", "enunciado": " "}, "Escribe la pregunta."),
        ({"tipo": "seccion", "enunciado": ""}, "Escribe el título."),
        ({"tipo": "abierta", "enunciado": "x", "puntos": "150"}, "Los puntos deben ser un número de 0 a 100."),
        ({"tipo": "opcion", "enunciado": "x", "puntos": "1", "opcion[0]": "Solo una"}, "Escribe al menos 2 opciones."),
        (
            {"tipo": "opcion", "enunciado": "x", "puntos": "1", "opcion[0]": "A", "opcion[1]": "B"},
            "Marca cuál es la opción correcta (solo una).",
        ),
        (
            {"tipo": "opcion", "enunciado": "x", "puntos": "1", "opcion[0]": "A", "opcion[1]": "B", "correctas[]": ["0", "1"]},
            "Marca cuál es la opción correcta (solo una).",
        ),
        (
            {"tipo": "multiple", "enunciado": "x", "puntos": "1", "opcion[0]": "A", "opcion[1]": "B"},
            "Marca las opciones correctas.",
        ),
        ({"tipo": "vf", "enunciado": "x", "puntos": "1"}, "Elige si la respuesta correcta es Verdadero o Falso."),
        (
            {"tipo": "cuadricula", "enunciado": "x", "puntos": "1", "filas": "Una", "columnas": "Solo una"},
            "Escribe al menos 1 fila y 2 columnas (una por línea).",
        ),
    ],
)
def test_preguntas_incorrectas(cliente_de, docente, modulo, clase, datos, mensaje):
    f = nuevo_formulario(clase, publicado=False)
    c = cliente_de(docente)
    r = agregar(c, f, **datos)
    assert r["Location"] == reverse("formularios:ver", args=[f.pk]) + "#nueva"
    assert mensaje in c.get(r["Location"]).content.decode()
    assert Pregunta.objects.count() == 0


def test_en_una_encuesta_las_preguntas_no_llevan_respuesta_correcta_ni_puntos(cliente_de, docente, modulo, clase):
    f = nuevo_formulario(clase, modo="encuesta", publicado=False)
    c = cliente_de(docente)
    agregar(c, f, tipo="opcion", enunciado="¿Cómo te fue?", **{"opcion[0]": "Bien", "opcion[1]": "Mal", "correctas[]": "0"})
    p = Pregunta.objects.get()
    assert p.puntos == 0 and not any(o.correcta for o in p.todas_las_opciones.all()) and p.explicacion == ""
    html = c.get(reverse("formularios:ver", args=[f.pk])).content.decode()
    assert "Encuesta" in html and "puntos</span>" not in html and "punto</span>" not in html and "Correcta:" not in html


def test_otros_tipos_de_pregunta(cliente_de, docente, modulo, clase):
    f = nuevo_formulario(clase, publicado=False)
    c = cliente_de(docente)
    agregar(c, f, tipo="vf", enunciado="Verdadero o falso", puntos="1", vf_correcta="f", obligatoria="1")
    agregar(c, f, tipo="corta", enunciado="Corta", puntos="1", aceptadas="  uno \n\n dos ")
    agregar(
        c,
        f,
        tipo="escala",
        enunciado="Escala",
        puntos="0",
        escala_min="0",
        escala_max="99",
        etiqueta_min="Nada",
        etiqueta_max="Mucho",
    )
    agregar(c, f, tipo="cuadricula", enunciado="Cuadrícula", puntos="0", filas="Puntualidad\nLimpieza", columnas="Bien\nMal")
    agregar(c, f, tipo="seccion", enunciado="Parte 2", obligatoria="1")
    vf, corta, escala, cuadricula, seccion = Pregunta.objects.order_by("orden")
    assert [(o.texto, o.correcta) for o in vf.todas_las_opciones.all()] == [("Verdadero", False), ("Falso", True)]
    assert corta.respuestas_aceptadas == "uno\ndos"
    assert (escala.escala_min, escala.escala_max, escala.etiqueta_min, escala.etiqueta_max) == (0, 10, "Nada", "Mucho")
    assert [(o.grupo, o.texto) for o in cuadricula.todas_las_opciones.all()] == [
        ("fila", "Puntualidad"), ("fila", "Limpieza"), ("columna", "Bien"), ("columna", "Mal"),
    ]  # fmt: skip
    assert seccion.obligatoria is False and seccion.puntos == 0


def test_pregunta_con_imagen(cliente_de, docente, modulo, clase):
    f = nuevo_formulario(clase, publicado=False)
    c = cliente_de(docente)
    agregar(c, f, tipo="abierta", enunciado="Mira la foto", puntos="1", imagen=muestras.png("corte.png"))
    p = Pregunta.objects.get()
    assert p.imagen_ruta and (Path(settings.MEDIA_ROOT) / p.imagen_ruta).is_file()
    r = c.get(reverse("formularios:pregunta_imagen", args=[p.pk]))
    assert r.status_code == 200 and r["Content-Type"] == "image/png" and "inline" in r["Content-Disposition"]
    html = c.get(reverse("formularios:ver", args=[f.pk])).content.decode()
    assert reverse("formularios:pregunta_imagen", args=[p.pk]) in html


def test_la_imagen_debe_ser_una_foto(cliente_de, docente, modulo, clase):
    f = nuevo_formulario(clase, publicado=False)
    c = cliente_de(docente)
    r = agregar(c, f, tipo="abierta", enunciado="x", puntos="1", imagen=muestras.pdf("no-es-foto.pdf"))
    assert "La imagen debe ser una foto (JPG, PNG o WEBP)." in c.get(r["Location"]).content.decode()
    assert Pregunta.objects.count() == 0


def test_cambiar_una_pregunta(cliente_de, docente, modulo, clase, examen):
    p = examen.preguntas.get(tipo="opcion")
    c = cliente_de(docente)
    html = c.get(reverse("formularios:pregunta_editar", args=[p.pk])).content.decode()
    assert (
        "Cambiar pregunta" in html
        and "¿Qué se usa para desenredar?" in html
        and "Guardar cambios" in html
        and 'value="Peine ancho"' in html
    )
    r = c.post(
        reverse("formularios:pregunta_actualizar", args=[p.pk]),
        {
            "tipo": "opcion",
            "enunciado": "Nuevo texto",
            "puntos": "5",
            "obligatoria": "1",
            "opcion[0]": "Uno",
            "opcion[1]": "Dos",
            "correctas[]": "0",
        },
    )
    assert r["Location"] == reverse("formularios:ver", args=[examen.pk]) + f"#p{p.pk}"
    p.refresh_from_db()
    assert p.enunciado == "Nuevo texto"
    assert [(o.texto, o.correcta) for o in p.todas_las_opciones.all()] == [("Uno", True), ("Dos", False)]


def test_quitar_o_cambiar_la_imagen_borra_el_archivo_anterior(
    cliente_de, docente, modulo, clase, django_capture_on_commit_callbacks
):
    f = nuevo_formulario(clase, publicado=False)
    c = cliente_de(docente)
    agregar(c, f, tipo="abierta", enunciado="x", puntos="1", imagen=muestras.png())
    p = Pregunta.objects.get()
    vieja = Path(settings.MEDIA_ROOT) / p.imagen_ruta
    datos = {"tipo": "abierta", "enunciado": "x", "puntos": "1"}
    with django_capture_on_commit_callbacks(execute=True):
        c.post(reverse("formularios:pregunta_actualizar", args=[p.pk]), {**datos, "imagen": muestras.png("nueva.png")})
    p.refresh_from_db()
    nueva = Path(settings.MEDIA_ROOT) / p.imagen_ruta
    assert not vieja.exists() and nueva.is_file()
    with django_capture_on_commit_callbacks(execute=True):
        c.post(reverse("formularios:pregunta_actualizar", args=[p.pk]), {**datos, "quitar_imagen": "1"})
    p.refresh_from_db()
    assert p.imagen_ruta == "" and not nueva.exists()


def test_duplicar_una_pregunta(cliente_de, docente, modulo, clase, examen):
    primera = examen.preguntas.order_by("orden").first()
    primera.imagen_ruta = "2026/10/foto.png"
    primera.save()
    c = cliente_de(docente)
    r = c.post(reverse("formularios:pregunta_duplicar", args=[primera.pk]))
    copia = Pregunta.objects.get(pk=int(r["Location"].split("#p")[1]))
    assert copia.enunciado == primera.enunciado and copia.orden == primera.orden + 1
    assert [o.texto for o in copia.todas_las_opciones.all()] == [o.texto for o in primera.todas_las_opciones.all()]
    assert list(examen.preguntas.values_list("orden", flat=True)) == [1, 2, 3, 4, 5]  # las demás bajaron un lugar
    assert "Pregunta copiada. Cámbiala con «Cambiar»." in c.get(r["Location"]).content.decode()


def test_la_copia_de_una_pregunta_tiene_su_propia_imagen(cliente_de, docente, modulo, clase, django_capture_on_commit_callbacks):
    f = nuevo_formulario(clase, publicado=False)
    c = cliente_de(docente)
    agregar(c, f, tipo="abierta", enunciado="x", puntos="1", imagen=muestras.png())
    original = Pregunta.objects.get()
    c.post(reverse("formularios:pregunta_duplicar", args=[original.pk]))
    copia = Pregunta.objects.exclude(pk=original.pk).get()
    assert copia.imagen_ruta and copia.imagen_ruta != original.imagen_ruta
    with django_capture_on_commit_callbacks(execute=True):
        original.delete()
    assert (Path(settings.MEDIA_ROOT) / copia.imagen_ruta).is_file()  # la copia conserva su imagen


def test_mover_y_borrar_preguntas(cliente_de, docente, modulo, clase, examen):
    p1, p2, p3, p4 = examen.preguntas.order_by("orden")
    c = cliente_de(docente)
    c.post(reverse("formularios:pregunta_mover", args=[p3.pk]), {"dir": "arriba"})
    assert [p.pk for p in examen.preguntas.order_by("orden")] == [p1.pk, p3.pk, p2.pk, p4.pk]
    c.post(reverse("formularios:pregunta_mover", args=[p1.pk]), {"dir": "arriba"})  # ya es la primera
    c.post(reverse("formularios:pregunta_mover", args=[p1.pk]), {"dir": "abajo"})
    assert [p.pk for p in examen.preguntas.order_by("orden")] == [p3.pk, p1.pk, p2.pk, p4.pk]
    r = c.post(reverse("formularios:pregunta_eliminar", args=[p1.pk]))
    assert "Pregunta borrada." in c.get(r["Location"]).content.decode()
    assert examen.preguntas.count() == 3 and not Opcion.objects.filter(pregunta=p1).exists()


def test_editor_con_todas_las_preguntas(cliente_de, docente, modulo, clase, examen):
    html = cliente_de(docente).get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert "4 preguntas · 20 puntos" in html and "Pregunta 4" in html and "5 puntos" in html
    assert (
        "A)&nbsp;Navaja" in html and "Correcta:" in html and "Respuesta correcta:" in html and "degrafilado · degradado" in html
    )


def test_no_se_pueden_cambiar_las_preguntas_si_ya_hay_respuestas(cliente_de, docente, rosa, modulo, clase, examen):
    p = examen.preguntas.first()
    Intento.objects.create(formulario=examen, alumno=rosa, fin=timezone.now(), revisado=True)
    c = cliente_de(docente)
    html = c.get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert "Las preguntas ya no se pueden cambiar." in html and "Agregar pregunta" not in html and "Cambiar</a>" not in html
    mensaje = "Ya hay alumnos que respondieron: no se pueden cambiar las preguntas."
    intentos = [
        lambda: agregar(c, examen, tipo="abierta", enunciado="x", puntos="1"),
        lambda: c.get(reverse("formularios:pregunta_editar", args=[p.pk])),
        lambda: c.post(
            reverse("formularios:pregunta_actualizar", args=[p.pk]), {"tipo": "abierta", "enunciado": "x", "puntos": "1"}
        ),
        lambda: c.post(reverse("formularios:pregunta_eliminar", args=[p.pk])),
        lambda: c.post(reverse("formularios:pregunta_duplicar", args=[p.pk])),
        lambda: c.post(reverse("formularios:pregunta_mover", args=[p.pk]), {"dir": "abajo"}),
        lambda: c.get(reverse("formularios:importar", args=[examen.pk])),
    ]
    for intentar in intentos:  # cada intento se sigue enseguida: el mensaje se muestra una sola vez
        r = intentar()
        assert r.status_code == 302 and r["Location"] == reverse("formularios:ver", args=[examen.pk])
        assert mensaje in c.get(r["Location"]).content.decode()
    assert examen.preguntas.count() == 4


def test_solo_el_docente_arma_las_preguntas(cliente_de, rosa, otro_docente, admin, modulo, clase, examen):
    p = examen.preguntas.first()
    for quien in (rosa, otro_docente, admin):
        c = cliente_de(quien)
        assert agregar(c, examen, tipo="abierta", enunciado="x", puntos="1").status_code == 403
        assert c.get(reverse("formularios:pregunta_editar", args=[p.pk])).status_code == 403
        assert c.post(reverse("formularios:pregunta_eliminar", args=[p.pk])).status_code == 403
        assert c.post(reverse("formularios:publicar", args=[examen.pk]), {"publicar": "0"}).status_code == 403
        assert c.post(reverse("formularios:eliminar", args=[examen.pk])).status_code == 403
        assert c.get(reverse("formularios:editar", args=[examen.pk])).status_code == 403
    assert examen.preguntas.count() == 4 and Formulario.objects.filter(publicado=True).count() == 1


# ===================================================================== Publicar, ocultar y borrar


def test_publicar_necesita_preguntas(cliente_de, docente, modulo, clase):
    f = nuevo_formulario(clase, publicado=False)
    c = cliente_de(docente)
    r = c.post(reverse("formularios:publicar", args=[f.pk]), {"publicar": "1"})
    assert "Agrega al menos una pregunta antes de publicar." in c.get(r["Location"]).content.decode()
    f.refresh_from_db()
    assert f.publicado is False
    pregunta(f, "seccion", "Solo un título", puntos=0)
    c.post(reverse("formularios:publicar", args=[f.pk]), {"publicar": "1"})
    f.refresh_from_db()
    assert f.publicado is False  # los títulos no cuentan como preguntas


def test_publicar_avisa_a_los_alumnos_y_se_puede_ocultar(cliente_de, docente, rosa, luis, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(publicado=False)
    c = cliente_de(docente)
    r = c.post(reverse("formularios:publicar", args=[examen.pk]), {"publicar": "1"})
    assert "¡Publicado! Tus alumnos ya lo ven en su Inicio." in c.get(r["Location"]).content.decode()
    examen.refresh_from_db()
    assert examen.publicado is True
    assert Notificacion.objects.filter(usuario=rosa, mensaje="Nuevo formulario para responder: Examen de bioseguridad").exists()
    assert Notificacion.objects.filter(usuario=luis).count() == 1
    r = c.post(reverse("formularios:publicar", args=[examen.pk]), {"publicar": "0"})
    assert "Oculto. Tus alumnos ya no lo ven." in c.get(r["Location"]).content.decode()
    c.post(reverse("formularios:publicar", args=[examen.pk]), {"publicar": "1"})  # otra vez publicado: no se avisa de nuevo
    assert Notificacion.objects.filter(usuario=rosa).count() == 2


def test_no_se_avisa_si_la_clase_todavia_no_empieza(cliente_de, docente, rosa, modulo, clase):
    Clase.objects.filter(pk=clase.pk).update(fecha_inicio=timezone.localdate() + timedelta(days=10))
    f = nuevo_formulario(clase, publicado=False)
    pregunta(f, "abierta", "x", puntos=1)
    cliente_de(docente).post(reverse("formularios:publicar", args=[f.pk]), {"publicar": "1"})
    assert Notificacion.objects.count() == 0


def test_borrar_el_formulario_lo_manda_a_la_papelera(cliente_de, docente, rosa, modulo, clase, examen):
    c = cliente_de(docente)
    r = c.post(reverse("formularios:eliminar", args=[examen.pk]))
    assert r["Location"] == reverse("academico:clase", args=[clase.pk])
    assert "Formulario enviado a la papelera. Puedes recuperarlo durante 30 días." in c.get(r["Location"]).content.decode()
    assert Formulario.objects.count() == 0 and Formulario.todos.get().eliminado is not None
    assert cliente_de(docente).get(reverse("formularios:ver", args=[examen.pk])).status_code == 404
    assert cliente_de(rosa).get(reverse("formularios:ver", args=[examen.pk])).status_code == 404
    papelera = c.get(reverse("academico:papelera", args=[modulo.pk])).content.decode()
    assert "Examen de bioseguridad" in papelera and "Formulario" in papelera
    # se recupera con todo lo que tenía
    c.post(reverse("academico:papelera", args=[modulo.pk]), {"tipo": "formulario", "item": examen.pk})
    assert Formulario.objects.count() == 1 and Formulario.objects.get().preguntas.count() == 4


# ===================================================================== El alumno: portada y empezar


def test_portada_para_el_alumno(cliente_de, rosa, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(tiempo_minutos=30, intentos_max=2, instrucciones="Lee con calma.")
    html = cliente_de(rosa).get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert "Examen" in html and "4 preguntas" in html and "Tienes 30 minutos" in html and "2 intentos" in html
    assert (
        "Lee con calma." in html and "Verás un reloj arriba" in html and "Puedes responder 2 veces. Vale tu mejor nota." in html
    )
    assert "Empezar el examen" in html and "Al empezar corre el reloj: tienes 30 minutos. ¿Empezamos?" in html
    assert "Cambiar" not in html and "Respuestas</a>" not in html  # no es la pantalla del docente


def test_portada_desde_el_inicio_vuelve_al_inicio(cliente_de, rosa, modulo, clase, examen):
    html = cliente_de(rosa).get(reverse("formularios:ver", args=[examen.pk]) + "?desde=inicio").content.decode()
    assert f'href="{reverse("nucleo:inicio")}"' in html


def test_el_alumno_no_ve_lo_que_no_esta_publicado_ni_de_clases_cerradas_para_el(
    cliente_de, rosa, forastero, modulo, clase, examen
):
    c = cliente_de(rosa)
    Formulario.objects.filter(pk=examen.pk).update(publicado=False)
    assert c.get(reverse("formularios:ver", args=[examen.pk])).status_code == 404
    Formulario.objects.filter(pk=examen.pk).update(publicado=True)
    Clase.objects.filter(pk=clase.pk).update(fecha_inicio=timezone.localdate() + timedelta(days=5))
    assert c.get(reverse("formularios:ver", args=[examen.pk])).status_code == 404
    Clase.objects.filter(pk=clase.pk).update(fecha_inicio=None, visible=False)
    assert c.get(reverse("formularios:ver", args=[examen.pk])).status_code == 404
    Clase.objects.filter(pk=clase.pk).update(visible=True)
    assert cliente_de(forastero).get(reverse("formularios:ver", args=[examen.pk])).status_code == 403  # no es del módulo
    assert Client().get(reverse("formularios:ver", args=[examen.pk])).status_code == 302  # sin sesión


def test_portada_cuando_todavia_no_abre_o_ya_cerro(cliente_de, rosa, modulo, clase, examen):
    c = cliente_de(rosa)
    Formulario.objects.filter(pk=examen.pk).update(fecha_inicio=timezone.now() + timedelta(days=2))
    html = c.get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert "Todavía no se puede responder. Se abre el" in html and "Empezar el examen" not in html
    Formulario.objects.filter(pk=examen.pk).update(fecha_inicio=None, fecha_limite=timezone.now() - timedelta(hours=1))
    assert "La fecha ya pasó." in c.get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert c.post(reverse("formularios:empezar", args=[examen.pk])).status_code == 302
    assert Intento.objects.count() == 0


def test_empezar_crea_el_intento_y_se_puede_seguir(cliente_de, rosa, modulo, clase, examen):
    c = cliente_de(rosa)
    r = c.post(reverse("formularios:empezar", args=[examen.pk]))
    i = Intento.objects.get()
    assert r["Location"] == reverse("formularios:intento", args=[i.pk]) and i.fin is None
    c.post(reverse("formularios:empezar", args=[examen.pk]))  # otra vez: sigue el mismo
    assert Intento.objects.count() == 1
    assert "Seguir respondiendo" in c.get(reverse("formularios:ver", args=[examen.pk])).content.decode()


def test_solo_los_alumnos_del_modulo_empiezan(cliente_de, docente, forastero, rosa, modulo, clase, examen):
    assert cliente_de(docente).post(reverse("formularios:empezar", args=[examen.pk])).status_code == 403
    assert cliente_de(forastero).post(reverse("formularios:empezar", args=[examen.pk])).status_code == 403
    assert cliente_de(rosa).get(reverse("formularios:empezar", args=[examen.pk])).status_code == 405
    assert Intento.objects.count() == 0


# ===================================================================== El alumno responde


def test_pantalla_para_responder(cliente_de, rosa, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(tiempo_minutos=30, instrucciones="Responde con calma.")
    c = cliente_de(rosa)
    c.post(reverse("formularios:empezar", args=[examen.pk]))
    i = Intento.objects.get()
    html = c.get(reverse("formularios:intento", args=[i.pk])).content.decode()
    assert "Pregunta 1 de 4" in html and "5 puntos" in html and "Responde con calma." in html and 'role="timer"' in html
    assert 1790 <= int(re.search(r'data-segundos="(\d+)"', html).group(1)) <= 1800  # 30 minutos
    assert 'type="radio"' in html and 'type="checkbox"' in html and "Peine ancho" in html and "Tu respuesta" in html
    assert 'data-total="4"' in html and "Enviar" in html and "Revisa tus respuestas antes de enviar" in html
    assert "Cambiar" not in html


def test_enviar_el_examen_todo_bien(cliente_de, docente, rosa, modulo, clase, examen):
    c = cliente_de(rosa)
    i, r = responder(c, examen, respuestas_correctas(examen))
    assert r["Location"] == reverse("formularios:intento", args=[i.pk])
    i.refresh_from_db()
    assert (
        i.fin is not None
        and i.revisado
        and i.nota == Decimal("20.00")
        and i.puntaje == Decimal("20.00")
        and i.puntaje_max == Decimal("20.00")
    )
    assert i.fuera_tiempo is False
    html = c.get(r["Location"]).content.decode()
    assert "¡Enviado! Tus respuestas se guardaron." in html and "Aprobado" in html and "20" in html and "Tu nota" in html
    assert html.count("Correcta</span>") >= 4 and "Tu respuesta" in html
    assert (
        Respuesta.objects.filter(intento=i).count() == 4 and not Respuesta.objects.filter(intento=i, puntos__isnull=True).exists()
    )


def test_el_examen_se_corrige_pregunta_por_pregunta(cliente_de, rosa, modulo, clase, examen):
    p1, p2, p3, p4 = examen.preguntas_completas()
    mala = {
        f"op[{p1.pk}]": p1.opciones[0].pk,
        f"op[{p2.pk}][]": [p2.opciones[0].pk],
        f"op[{p3.pk}]": p3.opciones[0].pk,
        f"txt[{p4.pk}]": "otra cosa",
    }
    i, _ = responder(cliente_de(rosa), examen, mala)
    i.refresh_from_db()
    # casillas incompletas, opción equivocada, verdadero correcto, corta mal → solo vale el verdadero
    assert i.nota == Decimal("5.00") and i.puntaje == Decimal("5.00")
    puntos = {r.pregunta_id: r.puntos for r in i.respuestas.all()}
    assert puntos == {p1.pk: Decimal("0"), p2.pk: Decimal("0"), p3.pk: Decimal("5"), p4.pk: Decimal("0")}


def test_las_casillas_piden_exactamente_las_correctas(cliente_de, rosa, luis, modulo, clase, examen):
    p2 = examen.preguntas.get(tipo="multiple")
    todas = list(p2.todas_las_opciones.values_list("pk", flat=True))
    sobrando = {**respuestas_correctas(examen), f"op[{p2.pk}][]": todas}  # marcó también la que no era
    i, _ = responder(cliente_de(rosa), examen, sobrando)
    assert i.respuestas.get(pregunta=p2).puntos == 0
    j, _ = responder(cliente_de(luis), examen, respuestas_correctas(examen))
    assert j.respuestas.get(pregunta=p2).puntos == 5


@pytest.mark.parametrize("escrito", ["degradado", " DeGrAdAdO ", "degrafilado", "¡Degradado!", "degradado\t"])
def test_la_respuesta_corta_ignora_mayusculas_tildes_y_signos(cliente_de, rosa, modulo, clase, escrito):
    f = nuevo_formulario(clase)
    p = pregunta(f, "corta", "Corte", puntos=20, aceptadas="Degrafilado\nDEGRADADO")
    i, _ = responder(cliente_de(rosa), f, {f"txt[{p.pk}]": escrito})
    i.refresh_from_db()
    assert i.nota == Decimal("20.00")


def test_normalizar_respuestas():
    assert calificar.normalizar("  ¡Árbol, ÑANDÚ!  ") == "arbol nandu"
    assert calificar.normalizar("a   b\tc") == "a b c"
    assert calificar.normalizar("") == ""


def test_la_respuesta_corta_sin_modelo_la_revisa_el_docente(cliente_de, rosa, modulo, clase):
    f = nuevo_formulario(clase)
    p = pregunta(f, "corta", "¿Cómo saludas al cliente?", puntos=20)
    i, _ = responder(cliente_de(rosa), f, {f"txt[{p.pk}]": "Buenos días"})
    i.refresh_from_db()
    assert i.nota is None and i.revisado is False and i.puntaje == 0 and i.puntaje_max == 20
    assert i.respuestas.get().puntos is None


def test_otra_marcada_en_examen_cuenta_como_error(cliente_de, rosa, modulo, clase):
    f = nuevo_formulario(clase)
    p = pregunta(f, "opcion", "¿Cuál?", [("Uno", True), ("Dos", False)], puntos=20, permite_otra=True)
    i, _ = responder(cliente_de(rosa), f, {f"op[{p.pk}]": "otra", f"otra[{p.pk}]": "Otra respuesta mía"})
    i.refresh_from_db()
    r = i.respuestas.get()
    assert i.nota == Decimal("0.00") and r.texto == "Otra respuesta mía" and r.opciones == ""
    html = cliente_de(rosa).get(reverse("formularios:intento", args=[i.pk])).content.decode()
    assert "Otra: Otra respuesta mía" in html


def test_faltan_preguntas_obligatorias(cliente_de, rosa, modulo, clase, examen):
    p1, p2, p3, p4 = examen.preguntas_completas()
    c = cliente_de(rosa)
    c.post(reverse("formularios:empezar", args=[examen.pk]))
    i = Intento.objects.get()
    r = c.post(
        reverse("formularios:intento", args=[i.pk]), {f"op[{p1.pk}]": p1.opciones[1].pk, f"txt[{p4.pk}]": "lo que ya escribí"}
    )
    html = r.content.decode()
    assert r.status_code == 200 and "Faltan responder las preguntas 2, 3." in html
    assert "lo que ya escribí" in html and re.search(rf'value="{p1.opciones[1].pk}"\s+checked', html)  # conserva lo marcado
    i.refresh_from_db()
    assert i.fin is None and not i.respuestas.exists()
    r = c.post(
        reverse("formularios:intento", args=[i.pk]),
        {f"op[{p1.pk}]": p1.opciones[1].pk, f"op[{p2.pk}][]": [p2.opciones[0].pk], f"txt[{p4.pk}]": "x"},
    )
    assert "Falta responder la pregunta 3." in r.content.decode()


def test_las_preguntas_no_obligatorias_pueden_quedar_vacias(cliente_de, rosa, modulo, clase):
    f = nuevo_formulario(clase)
    p = pregunta(f, "abierta", "Opcional", puntos=0, obligatoria=False)
    i, r = responder(cliente_de(rosa), f, {})
    i.refresh_from_db()
    assert i.fin is not None and p.pk and i.nota == 0  # sin puntos en total → nota 0


def test_no_se_envia_dos_veces(cliente_de, rosa, modulo, clase, examen):
    c = cliente_de(rosa)
    i, r = responder(c, examen, respuestas_correctas(examen))
    r2 = c.post(reverse("formularios:intento", args=[i.pk]), {})
    assert "Este formulario ya fue enviado." in c.get(r2["Location"]).content.decode()
    assert Respuesta.objects.filter(intento=i).count() == 4


def test_los_intentos_se_acaban(cliente_de, rosa, modulo, clase, examen):
    c = cliente_de(rosa)
    responder(c, examen, respuestas_correctas(examen))
    r = c.post(reverse("formularios:empezar", args=[examen.pk]))
    assert "Ya usaste todos tus intentos." in c.get(r["Location"]).content.decode()
    assert Intento.objects.count() == 1


def test_mejor_nota_entre_dos_intentos(cliente_de, rosa, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(intentos_max=2)
    p1, p2, p3, p4 = examen.preguntas_completas()
    c = cliente_de(rosa)
    flojo = {
        f"op[{p1.pk}]": p1.opciones[0].pk,
        f"op[{p2.pk}][]": [p2.opciones[2].pk],
        f"op[{p3.pk}]": p3.opciones[1].pk,
        f"txt[{p4.pk}]": "no sé",
    }
    primero, _ = responder(c, examen, flojo)
    html = c.get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert "Responder otra vez (te quedan 1)" in html and "Intento 1" not in html and "Mis respuestas" in html
    segundo, _ = responder(c, examen, respuestas_correctas(examen))
    assert primero.pk != segundo.pk
    html = c.get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert "Tu mejor nota" in html and "20" in html and "Aprobado" in html and "Intento 1" in html and "Intento 2" in html
    assert "Responder otra vez" not in html


def test_el_tiempo_de_un_examen(cliente_de, rosa, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(tiempo_minutos=10)
    c = cliente_de(rosa)
    c.post(reverse("formularios:empezar", args=[examen.pk]))
    i = Intento.objects.get()
    assert i.fin_de_tiempo == i.inicio + timedelta(minutes=10)
    # empezó hace 1 hora: ya se acabó el tiempo y no envió → se cierra en blanco
    Intento.objects.filter(pk=i.pk).update(inicio=timezone.now() - timedelta(hours=1))
    r = c.get(reverse("formularios:intento", args=[i.pk]))
    assert r["Location"] == reverse("formularios:intento", args=[i.pk])
    html = c.get(r["Location"]).content.decode()
    assert "Se acabó el tiempo." in html and "Se envió después del tiempo límite." in html
    i.refresh_from_db()
    assert i.fin is not None and i.fuera_tiempo and i.nota == Decimal("0.00")


def test_enviar_fuera_de_tiempo_se_marca(cliente_de, rosa, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(tiempo_minutos=10)
    c = cliente_de(rosa)
    c.post(reverse("formularios:empezar", args=[examen.pk]))
    i = Intento.objects.get()
    Intento.objects.filter(pk=i.pk).update(inicio=timezone.now() - timedelta(minutes=11))  # 1 min tarde: dentro de la tolerancia
    c.post(reverse("formularios:intento", args=[i.pk]), respuestas_correctas(examen))
    i.refresh_from_db()
    assert i.fuera_tiempo is False and i.nota == 20
    c.post(reverse("formularios:empezar", args=[examen.pk]))  # sin intentos: no hay otro
    Formulario.objects.filter(pk=examen.pk).update(intentos_max=2)
    c.post(reverse("formularios:empezar", args=[examen.pk]))
    j = Intento.objects.exclude(pk=i.pk).get()
    Intento.objects.filter(pk=j.pk).update(inicio=timezone.now() - timedelta(minutes=12, seconds=30))  # pasó la tolerancia
    c.post(reverse("formularios:intento", args=[j.pk]), respuestas_correctas(examen))
    j.refresh_from_db()
    assert j.fuera_tiempo is True and j.nota == 20  # se corrige igual, pero queda marcado
    assert (
        "Se envió después del tiempo límite."
        in cliente_de(rosa).get(reverse("formularios:intento", args=[j.pk])).content.decode()
    )


def test_si_se_acaba_el_tiempo_se_envia_aunque_falten_respuestas(cliente_de, rosa, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(tiempo_minutos=10)
    c = cliente_de(rosa)
    c.post(reverse("formularios:empezar", args=[examen.pk]))
    i = Intento.objects.get()
    Intento.objects.filter(pk=i.pk).update(inicio=timezone.now() - timedelta(minutes=10, seconds=5))
    r = c.post(reverse("formularios:intento", args=[i.pk]), {})  # el reloj lo envía solo, con lo que haya
    assert r.status_code == 302
    i.refresh_from_db()
    assert i.fin is not None and i.nota == 0


def test_mezclar_cambia_el_orden_pero_siempre_igual_para_un_intento(cliente_de, rosa, luis, modulo, clase):
    f = nuevo_formulario(clase, mezclar=True)
    for n in range(8):
        pregunta(f, "opcion", f"Pregunta número {n}", [("a", True), ("b", False), ("c", False), ("d", False)], puntos=1)
    pregunta(f, "vf", "Verdadero o falso", [("Verdadero", True), ("Falso", False)], puntos=1)
    c = cliente_de(rosa)
    c.post(reverse("formularios:empezar", args=[f.pk]))
    i = Intento.objects.get()
    url = reverse("formularios:intento", args=[i.pk])
    primero, segundo = c.get(url).content.decode(), c.get(url).content.decode()
    orden = lambda html: [int(x.split("<")[0]) for x in html.split("Pregunta número ")[1:]]  # noqa: E731
    assert orden(primero) == orden(segundo) and sorted(orden(primero)) == list(range(8))
    assert orden(primero) != list(range(8))  # con 8 preguntas es casi imposible que salgan en orden
    vf = primero.split("Verdadero o falso")[1]
    assert vf.index("Verdadero") < vf.index("Falso")  # verdadero/falso nunca se mezcla


def test_no_se_ve_la_conversacion_de_otro_alumno(cliente_de, rosa, luis, otro_docente, modulo, clase, examen):
    i, _ = responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    url = reverse("formularios:intento", args=[i.pk])
    assert cliente_de(luis).get(url).status_code == 403
    assert cliente_de(luis).post(url, {}).status_code == 403
    assert cliente_de(otro_docente).get(url).status_code == 403
    assert cliente_de(rosa).get(reverse("formularios:intento", args=[99999])).status_code == 404


def test_mostrar_respuestas_desactivado(cliente_de, docente, rosa, modulo, clase, examen):
    Formulario.objects.filter(pk=examen.pk).update(mostrar_respuestas=False)
    i, _ = responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    html = cliente_de(rosa).get(reverse("formularios:intento", args=[i.pk])).content.decode()
    assert "Tu profesor eligió no mostrar las respuestas." in html and "Peine ancho" not in html and "Tu nota" in html
    assert "Peine ancho" in cliente_de(docente).get(reverse("formularios:intento", args=[i.pk])).content.decode()


# ===================================================================== Otros tipos de pregunta al responder


def test_responder_todos_los_tipos(cliente_de, docente, rosa, modulo, clase):
    f = nuevo_formulario(clase, modo="encuesta")
    escala = pregunta(
        f, "escala", "¿Qué tanto te gustó?", puntos=0, escala_min=1, escala_max=5, etiqueta_min="Nada", etiqueta_max="Mucho"
    )
    fecha = pregunta(f, "fecha", "¿Qué día empezaste?", puntos=0)
    hora = pregunta(f, "hora", "¿A qué hora llegas?", puntos=0)
    abierta = pregunta(f, "abierta", "Cuéntanos más", puntos=0)
    desplegable = pregunta(f, "desplegable", "Tu turno", [("Mañana", False), ("Tarde", False)], puntos=0)
    cuadricula = pregunta(
        f,
        "cuadricula",
        "Califica",
        [("Puntualidad", False, "fila"), ("Limpieza", False, "fila"), ("Bien", False, "columna"), ("Mal", False, "columna")],
        puntos=0,
    )
    casillas = pregunta(
        f, "cuadricula_casillas", "Marca", [("Fila", False, "fila"), ("A", False, "columna"), ("B", False, "columna")], puntos=0
    )
    otra = pregunta(f, "multiple", "Elige", [("Uno", False), ("Dos", False)], puntos=0, permite_otra=True)
    c = cliente_de(rosa)
    c.post(reverse("formularios:empezar", args=[f.pk]))
    i = Intento.objects.get()
    html = c.get(reverse("formularios:intento", args=[i.pk])).content.decode()
    assert 'class="escala-etiqueta">Nada' in html and 'type="date"' in html and 'type="time"' in html and "<select" in html
    assert 'class="cuadricula"' in html and "Escribe aquí tu otra respuesta" in html and "Pregunta 8 de 8" in html
    cuadricula.cargar_opciones(), casillas.cargar_opciones(), desplegable.cargar_opciones(), otra.cargar_opciones()
    datos = {
        f"txt[{escala.pk}]": "4", f"txt[{fecha.pk}]": "2026-10-07", f"txt[{hora.pk}]": "08:30", f"txt[{abierta.pk}]": "Muy bien",
        f"op[{desplegable.pk}]": desplegable.opciones[1].pk,
        f"grid[{cuadricula.pk}][{cuadricula.filas[0].pk}]": cuadricula.columnas[0].pk,
        f"grid[{cuadricula.pk}][{cuadricula.filas[1].pk}]": cuadricula.columnas[1].pk,
        f"grid[{casillas.pk}][{casillas.filas[0].pk}][]": [c_.pk for c_ in casillas.columnas],
        f"op[{otra.pk}][]": [otra.opciones[0].pk, "otra"], f"otra[{otra.pk}]": "Tres",
    }  # fmt: skip
    r = c.post(reverse("formularios:intento", args=[i.pk]), datos)
    assert r.status_code == 302
    i.refresh_from_db()
    assert i.fin is not None and i.revisado and i.nota is None  # la encuesta no lleva nota
    respuestas = {r.pregunta_id: r for r in i.respuestas.all()}
    assert (
        respuestas[escala.pk].texto == "4" and respuestas[fecha.pk].texto == "2026-10-07" and respuestas[hora.pk].texto == "08:30"
    )
    assert calificar.grid_de(respuestas[cuadricula.pk]) == {
        cuadricula.filas[0].pk: [cuadricula.columnas[0].pk],
        cuadricula.filas[1].pk: [cuadricula.columnas[1].pk],
    }
    assert calificar.grid_de(respuestas[casillas.pk]) == {casillas.filas[0].pk: [x.pk for x in casillas.columnas]}
    assert respuestas[otra.pk].texto == "Tres" and respuestas[otra.pk].ids_marcados == [otra.opciones[0].pk]
    html = c.get(r["Location"]).content.decode()
    assert "¡Gracias! Tus respuestas se guardaron." in html or "¡Enviado! Tus respuestas se guardaron." in html
    assert (
        "Jueves" not in html
        and "Miércoles 7 de octubre de 2026" in html
        and "8:30 de la mañana" in html
        and "4 (de 1 a 5)" in html
    )
    assert "Puntualidad:" in html and "Bien" in html and "Otra: Tres" in html
    # el docente ve lo mismo y puede descargarlo
    assert (
        "Miércoles 7 de octubre de 2026" in cliente_de(docente).get(reverse("formularios:intento", args=[i.pk])).content.decode()
    )


def test_valores_invalidos_se_descartan(cliente_de, rosa, modulo, clase):
    f = nuevo_formulario(clase, modo="encuesta")
    escala = pregunta(f, "escala", "Escala", puntos=0, obligatoria=False, escala_min=1, escala_max=5)
    fecha = pregunta(f, "fecha", "Fecha", puntos=0, obligatoria=False)
    hora = pregunta(f, "hora", "Hora", puntos=0, obligatoria=False)
    opcion = pregunta(f, "opcion", "Opción", [("A", False), ("B", False)], puntos=0, obligatoria=False)
    i, _ = responder(
        cliente_de(rosa), f,
        {f"txt[{escala.pk}]": "9", f"txt[{fecha.pk}]": "2026-02-30", f"txt[{hora.pk}]": "25:99", f"op[{opcion.pk}]": "99999"},
    )  # fmt: skip
    i.refresh_from_db()
    assert i.fin is not None and i.respuestas.count() == 4
    assert all(not r.tiene_algo for r in i.respuestas.all())


def test_pregunta_de_archivo(cliente_de, docente, rosa, luis, otro_docente, admin, modulo, clase):
    f = nuevo_formulario(clase, modo="trabajo")
    p = pregunta(f, "archivo", "Sube una foto de tu corte", puntos=0)
    c = cliente_de(rosa)
    c.post(reverse("formularios:empezar", args=[f.pk]))
    i = Intento.objects.get()
    r = c.post(reverse("formularios:intento", args=[i.pk]), {})  # el archivo es obligatorio
    assert "Falta responder la pregunta 1." in r.content.decode()
    r = c.post(reverse("formularios:intento", args=[i.pk]), {f"archivo_{p.pk}": muestras.png("corte.png")})
    assert r.status_code == 302
    resp = i.respuestas.get()
    assert resp.archivo_nombre == "corte.png" and (Path(settings.MEDIA_ROOT) / resp.archivo_ruta).is_file()
    url = reverse("formularios:respuesta_archivo", args=[resp.pk])
    for quien in (rosa, docente, admin):
        ok_ = cliente_de(quien).get(url)
        assert ok_.status_code == 200 and ok_["Content-Type"] == "image/png"
    for quien in (luis, otro_docente):
        assert cliente_de(quien).get(url).status_code == 403
    assert Client().get(url).status_code == 302
    assert (
        "Archivo enviado en la pregunta 1"
        in cliente_de(docente).get(reverse("formularios:intento", args=[i.pk])).content.decode()
    )


def test_archivo_no_permitido_en_una_pregunta(cliente_de, rosa, modulo, clase):
    from django.core.files.uploadedfile import SimpleUploadedFile

    f = nuevo_formulario(clase, modo="trabajo")
    p = pregunta(f, "archivo", "Sube tu archivo", puntos=0)
    c = cliente_de(rosa)
    c.post(reverse("formularios:empezar", args=[f.pk]))
    i = Intento.objects.get()
    malo = SimpleUploadedFile("virus.exe", b"MZ....", content_type="application/octet-stream")
    r = c.post(reverse("formularios:intento", args=[i.pk]), {f"archivo_{p.pk}": malo})
    assert "Ese tipo de archivo no está permitido" in r.content.decode() and "Vuelve a elegir tus archivos." in r.content.decode()
    i.refresh_from_db()
    assert i.fin is None


def test_los_archivos_de_las_respuestas_se_borran_con_el_intento(
    cliente_de, rosa, modulo, clase, django_capture_on_commit_callbacks
):
    f = nuevo_formulario(clase, modo="trabajo")
    p = pregunta(f, "archivo", "Sube tu foto", puntos=0)
    i, _ = responder(cliente_de(rosa), f, {f"archivo_{p.pk}": muestras.png()})
    archivo = Path(settings.MEDIA_ROOT) / i.respuestas.get().archivo_ruta
    assert archivo.is_file()
    with django_capture_on_commit_callbacks(execute=True):
        modulo = f.clase.modulo
        modulo.eliminar_completo()
    assert not archivo.exists()


# ===================================================================== El docente revisa


def test_el_docente_revisa_lo_que_no_se_corrige_solo(cliente_de, docente, rosa, luis, modulo, clase):
    f = nuevo_formulario(clase)
    p1 = pregunta(f, "opcion", "Elige", [("Uno", True), ("Dos", False)], puntos=10)
    p2 = pregunta(f, "abierta", "Explica cómo recibes a un cliente.", puntos=10)
    i, _ = responder(
        cliente_de(rosa), f, {f"op[{p1.pk}]": p1.todas_las_opciones.get(correcta=True).pk, f"txt[{p2.pk}]": "Con una sonrisa"}
    )
    j, _ = responder(
        cliente_de(luis), f, {f"op[{p1.pk}]": p1.todas_las_opciones.get(correcta=False).pk, f"txt[{p2.pk}]": "Con prisa"}
    )
    i.refresh_from_db()
    assert i.nota is None and i.revisado is False and i.puntaje == 10 and i.puntaje_max == 20
    alumna = cliente_de(rosa).get(reverse("formularios:intento", args=[i.pk])).content.decode()
    assert "Tu profesor la está revisando" in alumna and "(sin contar lo que falta revisar)" in alumna and "Por revisar" in alumna

    c = cliente_de(docente)
    html = c.get(reverse("formularios:intento", args=[i.pk])).content.decode()
    assert (
        "Falta que la revises" in html
        and "Rosa Quispe Mamani" in html
        and f'name="puntos[{p2.pk}]"' in html
        and f'name="puntos[{p1.pk}]"' not in html
    )
    assert "Guardar y revisar el siguiente" in html and "Con una sonrisa" in html

    # el examen en el que falta revisar aparece en «Por calificar» y en el menú
    por_calificar = c.get(reverse("tareas:por_calificar")).content.decode()
    assert "Respondió el" in por_calificar and "Examen por revisar" in por_calificar

    r = c.post(
        reverse("formularios:revisar", args=[i.pk]),
        {
            f"puntos[{p2.pk}]": "7,5",
            f"comentario[{p2.pk}]": "Buena actitud",
            "comentario_general": "Bien hecho",
            "siguiente": "1",
        },
    )
    assert r["Location"] == reverse("formularios:intento", args=[j.pk])  # pasa a revisar al siguiente alumno
    assert "Revisión guardada de Rosa." in c.get(r["Location"]).content.decode()
    i.refresh_from_db()
    assert i.revisado and i.nota == Decimal("17.50") and i.puntaje == Decimal("17.50") and i.comentario == "Bien hecho"
    assert i.respuestas.get(pregunta=p2).comentario == "Buena actitud"
    assert Notificacion.objects.filter(usuario=rosa, mensaje="Tu profesor revisó: Examen de bioseguridad").exists()
    alumna = cliente_de(rosa).get(reverse("formularios:intento", args=[i.pk])).content.decode()
    assert (
        "17.5" in alumna
        and "Comentario del profesor:" in alumna
        and "Bien hecho" in alumna
        and "Buena actitud" in alumna
        and "Aprobado" in alumna
    )

    r = c.post(reverse("formularios:revisar", args=[j.pk]), {f"puntos[{p2.pk}]": "2", "siguiente": "1"})  # ya no quedan más
    assert r["Location"] == reverse("formularios:resultados", args=[f.pk]) + "?ver=personas"
    j.refresh_from_db()
    assert j.nota == Decimal("2.00")  # 0 de la primera + 2 de la que revisó el docente, sobre 20


def test_puntos_de_revision_fuera_de_rango(cliente_de, docente, rosa, modulo, clase):
    f = nuevo_formulario(clase)
    p = pregunta(f, "abierta", "Explica", puntos=10)
    i, _ = responder(cliente_de(rosa), f, {f"txt[{p.pk}]": "algo"})
    c = cliente_de(docente)
    r = c.post(reverse("formularios:revisar", args=[i.pk]), {f"puntos[{p.pk}]": "11"})
    assert "Los puntos de cada pregunta van de 0 a 10." in c.get(r["Location"]).content.decode()
    i.refresh_from_db()
    assert i.nota is None and not i.revisado


def test_calificar_un_trabajo(cliente_de, docente, rosa, luis, modulo, clase):
    f = nuevo_formulario(clase, modo="trabajo", titulo="Ficha de trabajo")
    p = pregunta(f, "abierta", "Describe el corte", puntos=0)
    i, _ = responder(cliente_de(rosa), f, {f"txt[{p.pk}]": "Degradado"})
    i.refresh_from_db()
    assert i.nota is None and i.revisado is False
    c = cliente_de(docente)
    html = c.get(reverse("formularios:intento", args=[i.pk])).content.decode()
    assert "Calificar este trabajo" in html and "Guardar nota y ver el siguiente" in html and "Falta que la revises" in html
    for malo in ("21", "-1", "abc", ""):
        r = c.post(reverse("formularios:revisar", args=[i.pk]), {"nota": malo})
        assert "La nota debe ser un número de 0 a 20." in c.get(r["Location"]).content.decode()
    r = c.post(reverse("formularios:revisar", args=[i.pk]), {"nota": "16,5", "comentario_general": "Muy limpio"})
    assert r["Location"] == reverse("formularios:resultados", args=[f.pk]) + "?ver=personas"
    i.refresh_from_db()
    assert i.nota == Decimal("16.50") and i.revisado and i.comentario == "Muy limpio"
    assert "Trabajo" in cliente_de(rosa).get(reverse("formularios:ver", args=[f.pk])).content.decode()
    assert "Muy limpio" in cliente_de(rosa).get(reverse("formularios:intento", args=[i.pk])).content.decode()


def test_solo_el_docente_del_modulo_revisa(cliente_de, rosa, luis, otro_docente, admin, modulo, clase):
    f = nuevo_formulario(clase, modo="trabajo")
    pregunta(f, "abierta", "x", puntos=0)
    i, _ = responder(cliente_de(rosa), f, {})
    for quien in (rosa, luis, otro_docente, admin):
        assert cliente_de(quien).post(reverse("formularios:revisar", args=[i.pk]), {"nota": "20"}).status_code == 403
    i.refresh_from_db()
    assert i.nota is None


def test_el_docente_no_ve_lo_que_el_alumno_todavia_responde(cliente_de, docente, rosa, modulo, clase, examen):
    c = cliente_de(rosa)
    c.post(reverse("formularios:empezar", args=[examen.pk]))
    i = Intento.objects.get()
    c_docente = cliente_de(docente)
    r = c_docente.get(reverse("formularios:intento", args=[i.pk]))
    assert r["Location"] == reverse("formularios:resultados", args=[examen.pk]) + "?ver=personas"
    assert "Ese alumno todavía está respondiendo." in c_docente.get(r["Location"]).content.decode()


def test_la_encuesta_no_lleva_nota(cliente_de, docente, rosa, modulo, clase):
    f = nuevo_formulario(clase, modo="encuesta", titulo="¿Cómo vamos?", mensaje_final="¡Gracias por tu opinión!")
    p = pregunta(f, "abierta", "Tu opinión", puntos=0)
    c = cliente_de(rosa)
    assert "Empezar a responder" in c.get(reverse("formularios:ver", args=[f.pk])).content.decode()
    i, r = responder(c, f, {f"txt[{p.pk}]": "Todo bien"})
    html = c.get(r["Location"]).content.decode()
    assert "¡Gracias por tu opinión!" in html and "Tu nota" not in html and "de 20" not in html
    assert "Ya respondiste esta encuesta. ¡Gracias!" in c.get(reverse("formularios:ver", args=[f.pk])).content.decode()
    assert "Por revisar" not in c.get(reverse("formularios:ver", args=[f.pk])).content.decode()
    assert "Falta que la revises" not in cliente_de(docente).get(reverse("formularios:intento", args=[i.pk])).content.decode()


# ===================================================================== Respuestas, resultados y descarga


def test_resultados_por_persona_y_resumen(cliente_de, docente, rosa, luis, forastero, modulo, clase, examen):
    p1, p2, p3, p4 = examen.preguntas_completas()
    c = cliente_de(docente)
    vacio = c.get(reverse("formularios:resultados", args=[examen.pk])).content.decode()
    assert "0/2" in vacio and "Todavía nadie respondió." in vacio and "Descargar para Excel" in vacio

    responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    mala = {
        f"op[{p1.pk}]": p1.opciones[0].pk,
        f"op[{p2.pk}][]": [p2.opciones[0].pk],
        f"op[{p3.pk}]": p3.opciones[1].pk,
        f"txt[{p4.pk}]": "no sé",
    }
    responder(cliente_de(luis), examen, mala)

    resumen = c.get(reverse("formularios:resultados", args=[examen.pk])).content.decode()
    assert "2/2" in resumen and "Promedio" in resumen and "10" in resumen and "Aprobaron" in resumen
    assert "2 respuestas" in resumen and "Peine ancho" in resumen and "50%" in resumen and "100%" in resumen
    personas = c.get(reverse("formularios:resultados", args=[examen.pk]) + "?ver=personas").content.decode()
    assert "Quispe Mamani, Rosa" in personas and "Nota 20" in personas and "Nota 0" in personas and "Paz, Luis" in personas
    assert "Por persona" in personas and 'aria-current="page">Por persona' in personas
    assert "Julia" not in personas  # la forastera no es del módulo


def test_resultados_con_alumnos_que_no_respondieron(cliente_de, docente, rosa, luis, modulo, clase, examen):
    responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    personas = cliente_de(docente).get(reverse("formularios:resultados", args=[examen.pk]) + "?ver=personas").content.decode()
    assert "No respondió" in personas and "Todavía no" in personas and "1 vez" in personas


def test_resumen_de_cada_tipo_de_pregunta(cliente_de, docente, rosa, luis, modulo, clase):
    f = nuevo_formulario(clase, modo="encuesta")
    escala = pregunta(f, "escala", "Escala", puntos=0, obligatoria=False, escala_min=1, escala_max=3)
    cuadricula = pregunta(
        f,
        "cuadricula",
        "Cuadrícula",
        [("Fila uno", False, "fila"), ("Bien", False, "columna"), ("Mal", False, "columna")],
        puntos=0,
        obligatoria=False,
    )
    abierta = pregunta(f, "abierta", "Abierta", puntos=0, obligatoria=False)
    fecha = pregunta(f, "fecha", "Fecha", puntos=0, obligatoria=False)
    otra = pregunta(f, "opcion", "Con otra", [("Uno", False), ("Dos", False)], puntos=0, obligatoria=False, permite_otra=True)
    archivo = pregunta(f, "archivo", "Foto", puntos=0, obligatoria=False)
    cuadricula.cargar_opciones(), otra.cargar_opciones()
    responder(
        cliente_de(rosa), f,
        {
            f"txt[{escala.pk}]": "2", f"grid[{cuadricula.pk}][{cuadricula.filas[0].pk}]": cuadricula.columnas[0].pk, f"txt[{abierta.pk}]": "Me gustó mucho",
            f"txt[{fecha.pk}]": "2026-10-07", f"op[{otra.pk}]": "otra", f"otra[{otra.pk}]": "Tres", f"archivo_{archivo.pk}": muestras.png("foto.png"),
        },
    )  # fmt: skip
    responder(
        cliente_de(luis),
        f,
        {
            f"txt[{escala.pk}]": "2",
            f"op[{otra.pk}]": otra.opciones[0].pk,
            f"grid[{cuadricula.pk}][{cuadricula.filas[0].pk}]": cuadricula.columnas[1].pk,
        },
    )
    html = cliente_de(docente).get(reverse("formularios:resultados", args=[f.pk])).content.decode()
    assert "2 (100%)" in html and "Fila uno" in html and "Me gustó mucho" in html and "07/10/2026" in html and "foto.png" in html
    assert "Ver respuestas «Otra»" in html and "Tres" in html and "Sin respuestas todavía." not in html.split("Foto")[0]
    assert "Promedio" not in html  # una encuesta no tiene promedio


def test_descargar_las_respuestas(cliente_de, docente, rosa, luis, modulo, clase, examen):
    p1, p2, p3, p4 = examen.preguntas_completas()
    responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    Intento.objects.update(fin=timezone.now())
    r = cliente_de(docente).get(reverse("formularios:descargar", args=[examen.pk]))
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv") and r["X-Content-Type-Options"] == "nosniff"
    assert r["Content-Disposition"] == 'attachment; filename="respuestas-examen-de-bioseguridad.csv"'
    texto = r.content.decode("utf-8")
    assert texto.startswith("﻿")
    filas = list(csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";"))
    assert filas[0][:5] == ["Fecha", "Apellidos", "Nombres", "Correo / DNI", "Nota"] and len(filas[0]) == 9
    assert filas[1][1:5] == ["Quispe Mamani", "Rosa", "12345678", "20"] and filas[1][5] == "Peine ancho"
    assert filas[1][6] == "Guantes; Mascarilla" and filas[1][7] == "Verdadero" and filas[1][8] == "DEGRADADO"


def test_descargar_protege_de_formulas_de_excel(cliente_de, docente, rosa, modulo, clase):
    f = nuevo_formulario(clase, modo="encuesta")
    p = pregunta(f, "abierta", "Comentario", puntos=0)
    responder(cliente_de(rosa), f, {f"txt[{p.pk}]": '=HYPERLINK("http://malo")'})
    texto = cliente_de(docente).get(reverse("formularios:descargar", args=[f.pk])).content.decode().lstrip("﻿")
    assert "'=HYPERLINK" in texto and ";=HYPERLINK" not in texto


def test_descargar_una_encuesta_no_tiene_columna_de_nota(cliente_de, docente, rosa, modulo, clase):
    f = nuevo_formulario(clase, modo="encuesta")
    pregunta(f, "abierta", "Comentario", puntos=0, obligatoria=False)
    responder(cliente_de(rosa), f, {})
    cabecera = cliente_de(docente).get(reverse("formularios:descargar", args=[f.pk])).content.decode().lstrip("﻿").splitlines()[0]
    assert "Nota" not in cabecera


def test_el_alumno_no_ve_resultados_ni_descargas(cliente_de, rosa, luis, otro_docente, modulo, clase, examen):
    responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    for nombre in ("resultados", "descargar", "vista_previa"):
        assert cliente_de(rosa).get(reverse(f"formularios:{nombre}", args=[examen.pk])).status_code == 403
        assert cliente_de(otro_docente).get(reverse(f"formularios:{nombre}", args=[examen.pk])).status_code == 403
    assert cliente_de(luis).get(reverse("formularios:resultados", args=[examen.pk])).status_code == 403


def test_administracion_puede_ver_las_respuestas(cliente_de, admin, rosa, modulo, clase, examen):
    i, _ = responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    c = cliente_de(admin)
    editor = c.get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert "Publicar para mis alumnos" not in editor and "Agregar pregunta" not in editor and "Respuestas</a>" in editor
    assert c.get(reverse("formularios:resultados", args=[examen.pk])).status_code == 200
    assert c.get(reverse("formularios:descargar", args=[examen.pk])).status_code == 200
    html = c.get(reverse("formularios:intento", args=[i.pk])).content.decode()
    assert "Nota" in html and "Guardar" not in html  # puede mirar, no calificar


def test_el_editor_muestra_cuantos_acertaron_cada_pregunta(cliente_de, docente, rosa, luis, modulo, clase, examen):
    p1, p2, p3, p4 = examen.preguntas_completas()
    responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    responder(
        cliente_de(luis),
        examen,
        {
            f"op[{p1.pk}]": p1.opciones[1].pk,
            f"op[{p2.pk}][]": [p2.opciones[2].pk],
            f"op[{p3.pk}]": p3.opciones[1].pk,
            f"txt[{p4.pk}]": "no",
        },
    )
    html = cliente_de(docente).get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert "100% la respondió bien" in html and "50% la respondió bien" in html and ">0% la respondió bien" not in html


def test_vista_previa_del_docente(cliente_de, docente, modulo, clase, examen):
    html = cliente_de(docente).get(reverse("formularios:vista_previa", args=[examen.pk])).content.decode()
    assert "Vista previa: así lo verán tus alumnos." in html and "Enviar (desactivado en la vista previa)" in html
    assert "data-vista-previa" in html and "Pregunta 1 de 4" in html and 'role="timer"' not in html
    assert Intento.objects.count() == 0


def test_la_plantilla_de_preguntas(cliente_de, docente, admin, rosa):
    r = cliente_de(docente).get(reverse("formularios:plantilla"))
    assert r.status_code == 200 and r["Content-Disposition"] == 'attachment; filename="plantilla-preguntas.csv"'
    filas = list(csv.reader(io.StringIO(r.content.decode().lstrip("﻿")), delimiter=";"))
    assert filas[0][:3] == ["Tipo", "Pregunta", "Opción A"] and filas[1][0] == "opciones" and len(filas) == 7
    assert cliente_de(admin).get(reverse("formularios:plantilla")).status_code == 200
    assert cliente_de(rosa).get(reverse("formularios:plantilla")).status_code == 403
    assert Client().get(reverse("formularios:plantilla")).status_code == 302


# ===================================================================== Modelo


def test_nota_de_un_examen():
    assert calificar.nota_de(15, 20) == 15 and calificar.nota_de(1, 3) == 6.67 and calificar.nota_de(0, 0) == 0.0
    assert calificar.redondear(0.125, 2) == 0.13 and calificar.redondear(2.5, 0) == 3.0


def test_entrada_de_post_ordena_los_campos():
    from django.http import QueryDict

    post = QueryDict(
        "op[3]=7&op[4][]=1&op[4][]=2&txt[5]=hola&otra[3]=otro&grid[6][10]=1&grid[6][11][]=2&grid[6][11][]=3&malo[1]=x&csrfmiddlewaretoken=z"
    )
    assert calificar.entrada_de_post(post) == {
        "op": {3: ["7"], 4: ["1", "2"]}, "txt": {5: "hola"}, "otra": {3: "otro"}, "grid": {6: {10: ["1"], 11: ["2", "3"]}},
    }  # fmt: skip


def test_mezclar_es_estable():
    lista = list(range(20))
    assert calificar.mezclar(lista, 5) == calificar.mezclar(lista, 5) != calificar.mezclar(lista, 6)
    assert sorted(calificar.mezclar(lista, 5)) == lista and lista == list(range(20))


def test_el_formulario_sabe_si_esta_abierto(clase):
    f = nuevo_formulario(clase)
    assert f.abierto and not f.vencido
    Formulario.objects.filter(pk=f.pk).update(fecha_limite=timezone.now() - timedelta(minutes=1))
    f.refresh_from_db()
    assert not f.abierto and f.vencido
    Formulario.objects.filter(pk=f.pk).update(fecha_limite=timezone.now() + timedelta(days=1), publicado=False)
    f.refresh_from_db()
    assert not f.abierto


def test_el_boton_para_esconder_un_formulario_dice_a_quien_se_lo_esconde(cliente_de, docente, modulo, clase, examen):
    c = cliente_de(docente)
    html = c.get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert "Ocultar a mis alumnos" in html and "Publicar para mis alumnos" not in html
    Formulario.objects.filter(pk=examen.pk).update(publicado=False)
    html = c.get(reverse("formularios:ver", args=[examen.pk])).content.decode()
    assert "Publicar para mis alumnos" in html and "Ocultar a mis alumnos" not in html
