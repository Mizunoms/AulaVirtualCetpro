"""Animaciones: se pueden apagar («Reducir animaciones»), los logros se festejan y nada queda sin su versión de menos movimiento."""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import Preferencia
from apps.nucleo import ayuda

pytestmark = pytest.mark.django_db

RAIZ = Path(__file__).resolve().parent.parent
CSS = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
JS = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")


def guardar_preferencias(c, **extra):
    return c.post(reverse("cuentas:preferencias"), {"tamano_letra": "normal", **extra})


# ===================================================================== «Reducir animaciones» (Mi cuenta)


def test_las_animaciones_vienen_activadas_y_se_pueden_reducir(cliente_de, alumno):
    c = cliente_de(alumno)
    html = c.get(reverse("cuentas:cuenta")).content.decode()
    assert "Reducir animaciones" in html and 'name="reducir_movimiento"' in html
    assert "sin-animacion" not in c.get(reverse("nucleo:inicio")).content.decode().split("<body", 1)[1].split(">", 1)[0]

    guardar_preferencias(c, reducir_movimiento="1")
    assert Preferencia.objects.get(usuario=alumno).reducir_movimiento is True
    cuerpo = c.get(reverse("nucleo:inicio")).content.decode().split("<body", 1)[1].split(">", 1)[0]
    assert "sin-animacion" in cuerpo  # el CSS y el JS se apagan con esta clase
    assert re.search(r'name="reducir_movimiento"[^>]*checked', c.get(reverse("cuentas:cuenta")).content.decode())

    guardar_preferencias(c)  # sin marcar: vuelven las animaciones
    assert Preferencia.objects.get(usuario=alumno).reducir_movimiento is False


def test_reducir_animaciones_no_cambia_las_otras_preferencias(cliente_de, alumno):
    c = cliente_de(alumno)
    guardar_preferencias(c, alto_contraste="1", lectura_voz="1", reducir_movimiento="1", tamano_letra="grande")
    p = Preferencia.objects.get(usuario=alumno)
    assert (p.tamano_letra, p.alto_contraste, p.lectura_voz, p.reducir_movimiento) == ("grande", True, True, True)


def test_la_ayuda_menciona_las_animaciones():
    assert all(
        "animaciones" in paso.texto
        for pasos in ayuda.PASOS.values()
        for paso in pasos
        if paso.titulo == "Para ver y escuchar mejor"
    )


# ===================================================================== Qué se festeja (confeti) y qué no


def con_celebracion(html):
    return "data-celebrar" in html


def test_un_mensaje_normal_no_lleva_confeti(cliente_de, alumno):
    c = cliente_de(alumno)
    r = guardar_preferencias(c)  # «Listo, guardamos tus cambios.»
    html = c.get(r["Location"]).content.decode()
    assert "guardamos tus cambios" in html and not con_celebracion(html)


def test_entregar_una_tarea_se_festeja(cliente_de, alumno, docente):
    from apps.academico.models import Clase, Modulo
    from apps.tareas.models import Tarea

    from . import muestras

    modulo = Modulo.crear(nombre="Peluquería – M1", especialidad="Peluquería", periodo="2026-II", turno="mañana", docente=docente)
    modulo.matricular(alumno)
    t = Tarea.objects.create(clase=Clase.crear(modulo, "Corte"), titulo="Foto", fecha_limite=timezone.now() + timedelta(days=2))
    c = cliente_de(alumno)
    r = c.post(reverse("tareas:entregar", args=[t.pk]), {"foto": muestras.png("corte.png")})
    html = c.get(r["Location"]).content.decode()
    assert "¡Tarea entregada!" in html and con_celebracion(html)
    assert not con_celebracion(c.get(r["Location"]).content.decode())  # el mensaje se muestra una sola vez


def test_publicar_se_festeja_pero_ocultar_no(cliente_de, docente, rosa, modulo, clase, examen):
    from apps.formularios.models import Formulario

    c = cliente_de(docente)
    Formulario.objects.filter(pk=examen.pk).update(publicado=False)
    r = c.post(reverse("formularios:publicar", args=[examen.pk]), {"publicar": "1"})
    assert con_celebracion(c.get(r["Location"]).content.decode())
    r = c.post(reverse("formularios:publicar", args=[examen.pk]), {"publicar": "0"})
    html = c.get(r["Location"]).content.decode()
    assert "Oculto." in html and not con_celebracion(html)


def test_un_mensaje_de_error_nunca_se_festeja(cliente_de, alumno):
    c = cliente_de(alumno)
    r = c.post(reverse("cuentas:clave"), {"actual": "mala", "nueva": "abcdefg", "repetir": "abcdefg"})
    html = c.get(r["Location"].split("#")[0]).content.decode()
    assert "mensaje-error" in html and not con_celebracion(html)


# ===================================================================== Que todo se pueda apagar


def test_toda_animacion_usada_esta_definida():
    usadas = set(re.findall(r"animation:\s*([a-z][a-z-]*)", CSS)) - {"none"}
    definidas = set(re.findall(r"@keyframes\s+([a-z][a-z-]*)", CSS))
    assert usadas <= definidas, f"animaciones usadas pero sin @keyframes: {sorted(usadas - definidas)}"


def test_hay_version_de_menos_movimiento_por_el_aparato_y_por_la_preferencia():
    por_aparato = CSS.split("@media (prefers-reduced-motion: reduce)", 1)[1].split("}\n", 1)[0]
    assert "animation-duration" in por_aparato and "transition-duration" in por_aparato
    por_preferencia = re.search(
        r"body\.sin-animacion \*, body\.sin-animacion \*::before, body\.sin-animacion \*::after \{([^}]*)\}", CSS
    )
    assert (
        por_preferencia and "animation-duration" in por_preferencia.group(1) and "transition-duration" in por_preferencia.group(1)
    )
    assert "body.sin-animacion .confeti" in CSS and "@media print" in CSS


def test_el_javascript_respeta_menos_movimiento():
    assert "prefers-reduced-motion: reduce" in JS and "classList.contains('sin-animacion')" in JS
    # El confeti, los números que suben y la campana no corren si hay que reducir el movimiento
    assert re.search(r"var celebrar = function \(\) \{\s*if \(sinMovimiento\(\)", JS)
    assert "if (!sinMovimiento()) {\n    document.querySelectorAll('.hola-datos b')" in JS
    assert "!sinMovimiento() && !sessionStorage.getItem('campana-sonada')" in JS


def test_solo_se_animan_cosas_baratas_para_el_celular():
    """Las animaciones nuevas solo mueven transform y opacity (no width, height, top…): corren bien en celulares sencillos."""
    desde = CSS.index("/* ===== Animaciones")
    bloque = CSS[desde:]
    cuerpos = re.findall(r"@keyframes\s+[a-z-]+\s*\{(.*?)\n(?=@keyframes|\n)", bloque, re.S)
    assert len(cuerpos) >= 10  # que la revisión no quede vacía
    for cuerpo in cuerpos:
        assert not re.search(r"\b(width|height|top|left|margin|padding)\s*:", cuerpo), cuerpo
