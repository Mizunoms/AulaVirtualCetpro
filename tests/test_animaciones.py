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


# ===================================================================== Fondo vivo de la pantalla de entrada


def test_la_entrada_trae_el_fondo_vivo_como_adorno_con_su_boton_para_quitarlo(client):
    for url in (reverse("cuentas:login"), reverse("cuentas:registro")):
        html = client.get(url).content.decode()
        assert 'class="fondo-vivo" aria-hidden="true"' in html, url  # solo adorno: los lectores de pantalla no lo leen
        assert html.count('class="fondo-capa') >= 9 and "Quitar el movimiento del fondo" in html, url
        assert "data-fondo-pausa" in html and not re.findall(r"<script(?![^>]*\bsrc=)", html), url  # sin JS en línea


def test_las_capas_del_fondo_se_mueven_en_sentidos_opuestos_con_distinta_profundidad():
    html = (RAIZ / "templates" / "partials" / "fondo_vivo.html").read_text(encoding="utf-8")
    profundidades = [int(p) for p in re.findall(r'class="fondo-capa[^"]*" style="--prof: (-?\d+)"', html)]
    assert len(profundidades) == html.count('class="fondo-capa') >= 9  # todas traen su profundidad
    assert any(p < 0 for p in profundidades) and any(p > 0 for p in profundidades) and len(set(profundidades)) >= 6


def test_el_efecto_del_raton_y_el_de_flotar_no_van_en_el_mismo_elemento():
    """Si los dos usan `transform` en el mismo elemento, la animación pisa al ratón y el efecto no se ve."""
    desde = CSS.index("Entrada: fondo vivo")
    bloque = CSS[desde:]
    capa = re.search(r"\.fondo-capa \{([^}]*)\}", bloque).group(1)
    assert "var(--px" in capa and "animation" not in capa
    for clase in (".luz", ".figura", ".punto"):
        regla = re.search(r"\n\s*" + re.escape(clase) + r" \{([^}]*)\}", bloque).group(1)
        assert "animation:" in regla and "--px" not in regla, clase


def test_el_fondo_vivo_solo_se_ve_en_pantalla_ancha_y_se_detiene_o_esconde_cuando_corresponde():
    bloque = CSS[CSS.index("Entrada: fondo vivo") :]
    assert ".fondo-vivo, .fondo-pausa { display: none; }" in bloque
    assert bloque.index(".fondo-vivo, .fondo-pausa { display: none; }") < bloque.index("@media (min-width: 992px) {")
    assert ".fondo-quieto .luz, .fondo-quieto .figura, .fondo-quieto .punto { animation-play-state: paused; }" in bloque
    assert "@media (min-width: 992px) and (prefers-reduced-motion: reduce) { .fondo-pausa { display: none; } }" in bloque
    assert (
        "body.sin-animacion .fondo-pausa, body.alto-contraste .fondo-pausa, body.alto-contraste .fondo-vivo { display: none; }"
        in bloque
    )
    assert "backdrop-filter: blur" not in bloque and "filter: blur" not in bloque  # el desenfoque pesa en computadoras viejas


def test_el_javascript_del_fondo_respeta_el_aparato_el_dedo_y_la_eleccion_guardada():
    bloque = JS[JS.index("Fondo vivo de la entrada") : JS.index("Al enviar fotos o archivos")]
    assert "(hover: hover) and (pointer: fine) and (min-width: 992px)" in bloque  # solo ratón y pantalla ancha
    assert "ev.pointerType === 'touch'" in bloque and "sinMovimiento()" in bloque and "requestAnimationFrame" in bloque
    assert re.search(r"try \{ quieto = localStorage\.getItem\('fondo-quieto'\) === '1'; \} catch", bloque)
    assert re.search(r"try \{ localStorage\.setItem\('fondo-quieto', quieto \? '1' : '0'\); \} catch", bloque)
    assert "Poner el movimiento del fondo" in bloque and "Quitar el movimiento del fondo" in bloque


def test_el_fondo_trae_el_lienzo_del_cielo_y_los_utiles_escolares_que_flotan(client):
    html = client.get(reverse("cuentas:login")).content.decode()
    assert html.count("<canvas") == 1 and "data-cielo" in html
    assert html.count('class="figura"') == 7 and html.count('class="punto"') == 3  # cuaderno, lápiz, libro, regla…
    assert html.index("<canvas") < html.index('class="figura"')  # las figuras quedan por encima del cielo


def test_el_cielo_es_liviano_se_ve_igual_en_cada_visita_y_se_detiene_del_todo():
    cielo = JS[JS.index("Cielo de galaxia, dibujado") : JS.index("Fondo vivo de la entrada")]
    assert "tope: 200" in cielo and "fps: 38" in cielo  # la entrada: tope de estrellas y unos 38 cuadros por segundo
    assert "tope: 110" in cielo and "fps: 28" in cielo  # los banners y el tutorial: más calmados
    assert "1 / cfg.fps" in cielo
    assert "shadowBlur" not in cielo and "filter" not in cielo  # el desenfoque pesa en computadoras viejas
    assert "semilla = 20260; // la misma semilla" in cielo  # sin números al azar distintos en cada visita
    assert "cancelAnimationFrame" in cielo and "dibujar(0)" in cielo  # al detenerlo queda una imagen fija
    principal = JS[JS.index("Fondo vivo de la entrada") : JS.index("Al enviar fotos o archivos")]
    assert "cielo.correr(visible && !quieto && !sinMovimiento())" in principal
    assert "fondo.offsetWidth > 0" in principal  # en celular el fondo está escondido: el cielo no corre
    assert "cielo.mover(px, py)" in principal and "cielo.mover(0, 0)" in principal  # el ratón también lo mueve un poco


def test_el_lienzo_ocupa_todo_el_lado_de_la_marca_y_el_circulo_viejo_cede_su_lugar():
    bloque = CSS[CSS.index("Entrada: fondo vivo") :]
    assert re.search(r"\.estrellas \{[^}]*inset: 0[^}]*width: 100%[^}]*height: 100%", bloque)
    assert ".publica-lado::after { display: none; }" in bloque


# ===================================================================== El mismo cielo dentro del programa (solo donde se ve bien)


@pytest.fixture
def direccion(db):
    from apps.cuentas.models import Rol, Usuario

    from .conftest import CLAVE

    return Usuario.objects.create_user(correo="direccion@cetpro.com", nombres="Dirección", password=CLAVE, rol=Rol.DIRECCION)


def con_tutorial_visto(*personas):
    for p in personas:
        p.tutorial_visto = timezone.now()
        p.save(update_fields=["tutorial_visto"])


def test_los_banners_de_bienvenida_del_inicio_llevan_el_cielo(cliente_de, alumno, docente, admin, direccion):
    con_tutorial_visto(alumno, docente, admin, direccion)
    for persona, con_utiles in ((alumno, False), (docente, True), (admin, True), (direccion, True)):
        html = cliente_de(persona).get(reverse("nucleo:inicio")).content.decode()
        assert 'class="hola hola-cielo' in html or 'class="hola hola-alumno hola-cielo"' in html, persona.rol
        assert html.count("<canvas") == 1 and 'class="cielo-banner" aria-hidden="true"' in html, persona.rol
        assert ('class="figura figura-b1"' in html) is con_utiles, persona.rol  # el alumno ya tiene números a la derecha


def test_el_tutorial_lleva_una_franja_de_cielo_arriba(cliente_de, alumno):
    html = cliente_de(alumno).get(reverse("nucleo:inicio")).content.decode()  # la primera vez trae el tutorial
    assert 'id="tutorial"' in html and 'data-cielo-banner="tutorial"' in html and 'class="tutorial-cielo"' in html
    assert html.count("<canvas") == 2  # el del banner y el del tutorial
    assert "Paso <b data-paso>1</b>" in html and "data-punto" in html  # lo de siempre sigue ahí, encima del cielo


def test_el_cielo_no_va_en_listas_modulos_formularios_ni_ajustes(cliente_de, docente, alumno, modulo, clase):
    """Solo donde hay un fondo azul grande con poco texto: el resto del programa queda limpio."""
    con_tutorial_visto(alumno, docente)
    paginas = [
        (cliente_de(docente), reverse("academico:modulos")),
        (cliente_de(docente), reverse("academico:modulo", args=[modulo.pk])),
        (cliente_de(docente), reverse("academico:clase", args=[clase.pk])),
        (cliente_de(alumno), reverse("cuentas:cuenta")),
        (cliente_de(alumno), reverse("nucleo:ayuda")),
    ]
    for cliente, url in paginas:
        html = cliente.get(url).content.decode()
        assert "<canvas" not in html and "cielo-banner" not in html, url


def test_el_cielo_de_los_banners_se_detiene_se_esconde_y_se_adapta_al_celular():
    bloque = CSS[CSS.index("Cielo de galaxia dentro del programa") :]
    assert ".hola-cielo::before, .hola-cielo::after { display: none; }" in bloque
    assert ".cielo-banner .figura { display: none; }" in bloque  # los útiles solo en pantalla ancha
    assert bloque.index(".cielo-banner .figura { display: none; }") < bloque.index("@media (min-width: 992px)")
    assert "body.alto-contraste .cielo-banner, body.alto-contraste .tutorial-cielo canvas { display: none; }" in bloque
    assert "@media print { .cielo-banner, .tutorial-cielo canvas { display: none !important; } }" in bloque
    assert re.search(r"\.hola > \.cielo-banner \{[^}]*position: absolute[^}]*z-index: 0", bloque)  # detrás del texto


def test_el_javascript_de_los_banners_corre_solo_si_se_ve_y_respeta_menos_movimiento():
    bloque = JS[JS.index("Cielo de los banners de bienvenida") : JS.index("Al enviar fotos o archivos")]
    assert "sinMovimiento()" in bloque and "IntersectionObserver" in bloque and "ResizeObserver" in bloque
    assert "enPantalla" in bloque and "lienzo.dataset.cieloBanner === 'tutorial'" in bloque
    assert "estrecho" in JS and "ancho < 560" in JS  # en celular la galaxia se corre para no tapar el texto


def test_la_etiqueta_pequena_del_resumen_se_lee_sobre_el_azul():
    regla = re.search(r"\.hola-datos span \{[^}]*color: rgba\(255, 255, 255, ([.\d]+)\)", CSS)
    assert float(regla.group(1)) >= 0.95


def test_solo_se_animan_cosas_baratas_para_el_celular():
    """Las animaciones nuevas solo mueven transform y opacity (no width, height, top…): corren bien en celulares sencillos."""
    desde = CSS.index("/* ===== Animaciones")
    bloque = CSS[desde:]
    cuerpos = re.findall(r"@keyframes\s+[a-z-]+\s*\{(.*?)\n(?=@keyframes|\n)", bloque, re.S)
    assert len(cuerpos) >= 10  # que la revisión no quede vacía
    for cuerpo in cuerpos:
        assert not re.search(r"\b(width|height|top|left|margin|padding)\s*:", cuerpo), cuerpo
