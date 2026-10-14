"""Ayuda: tutorial de primera vez (alumno, docente, administración, dirección), resumen del sistema y «Repetir tutorial»."""

import re
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import Rol, Usuario
from apps.nucleo import ayuda

from .conftest import CLAVE

pytestmark = pytest.mark.django_db

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def direccion(db):
    return Usuario.objects.create_user(correo="direccion@cetpro.com", nombres="Dirección", password=CLAVE, rol=Rol.DIRECCION)


def inicio(cliente, query=""):
    return cliente.get(reverse("nucleo:inicio") + query).content.decode()


def ya_vio_el_tutorial(usuario):
    usuario.tutorial_visto = timezone.now()
    usuario.save(update_fields=["tutorial_visto"])


# ===================================================================== La primera vez


def test_la_primera_vez_el_tutorial_viene_con_el_inicio_de_cada_rol(cliente_de, alumno, docente, admin, direccion):
    for persona, rol in ((alumno, Rol.ALUMNO), (docente, Rol.DOCENTE), (admin, Rol.ADMIN), (direccion, Rol.DIRECCION)):
        html = inicio(cliente_de(persona))
        pasos = ayuda.PASOS[rol]
        assert 'id="tutorial"' in html and 'data-abrir="1"' in html, rol
        assert html.count("data-slide") == len(pasos), rol  # un bloque por paso
        assert f"de {len(pasos)}</span>" in html and "Saltar tutorial" in html and "Escuchar" in html, rol
        for paso in pasos:
            assert paso.titulo in html, (rol, paso.titulo)


def test_cada_rol_tiene_su_propio_tutorial():
    titulos = {rol: [p.titulo for p in pasos] for rol, pasos in ayuda.PASOS.items()}
    assert "Entregar una tarea con foto" in titulos[Rol.ALUMNO] and "Entregar una tarea con foto" not in titulos[Rol.DOCENTE]
    assert "Por calificar" in titulos[Rol.DOCENTE] and "Dejar una tarea" in titulos[Rol.DOCENTE]
    assert "Registro de actividad" in titulos[Rol.ADMIN] and "Personas" in titulos[Rol.ADMIN]
    for rol, lista in titulos.items():  # todos empiezan dándole la bienvenida y terminan diciendo dónde está la ayuda
        assert lista[0] == "Bienvenido al aula virtual" and lista[-1] == "Si te queda una duda", rol
    assert ayuda.pasos_de("rol-raro") == ayuda.PASOS[Rol.ALUMNO]


def test_el_tutorial_se_abre_solo_una_vez_aunque_no_lo_termine(cliente_de, alumno):
    c = cliente_de(alumno)
    assert alumno.tutorial_visto is None
    assert 'id="tutorial"' in inicio(c)  # la primera vez que ve su Inicio
    alumno.refresh_from_db()
    assert alumno.tutorial_visto is not None  # se marcó al mostrarlo, no al cerrarlo
    for _ in range(3):  # recargar la página, volver al Inicio, salir y entrar…: ya no se abre solo
        html = inicio(c)
        assert 'id="tutorial"' not in html and "data-slide" not in html
    # Sí sigue el botón para verlo otra vez
    assert "¿Necesitas ayuda?" in html and "Repetir tutorial" in html and "?tutorial=1" in html


def test_ver_otras_pantallas_antes_del_inicio_no_gasta_el_tutorial(cliente_de, alumno):
    c = cliente_de(alumno)
    c.get(reverse("cuentas:cuenta"))
    c.get(reverse("nucleo:ayuda"))
    alumno.refresh_from_db()
    assert alumno.tutorial_visto is None and 'id="tutorial"' in inicio(c)


def test_al_salir_y_volver_a_entrar_el_tutorial_no_vuelve(cliente_de, alumno, client):
    assert 'id="tutorial"' in inicio(cliente_de(alumno))
    client.post(reverse("cuentas:login"), {"usuario": alumno.dni, "clave": CLAVE, "tipo": "alumno"})
    assert 'id="tutorial"' not in client.get(reverse("nucleo:inicio")).content.decode()


def test_repetir_tutorial_lo_abre_aunque_ya_lo_haya_visto(cliente_de, docente):
    ya_vio_el_tutorial(docente)
    c = cliente_de(docente)
    assert 'id="tutorial"' not in inicio(c)
    html = inicio(c, "?tutorial=1")
    assert 'id="tutorial"' in html and 'data-abrir="1"' in html and "Dejar una tarea" in html
    assert 'id="tutorial"' not in inicio(c)  # y al volver al Inicio normal, otra vez cerrado


def test_pedir_el_tutorial_con_el_boton_la_primera_vez_tambien_cuenta_como_visto(cliente_de, alumno):
    c = cliente_de(alumno)
    assert 'id="tutorial"' in inicio(c, "?tutorial=1")
    alumno.refresh_from_db()
    assert alumno.tutorial_visto is not None and 'id="tutorial"' not in inicio(c)


def test_cada_persona_tiene_su_propia_marca(cliente_de, alumno, docente):
    inicio(cliente_de(alumno))
    docente.refresh_from_db()
    assert docente.tutorial_visto is None and 'id="tutorial"' in inicio(cliente_de(docente))


def test_ya_no_hay_aviso_al_servidor_al_cerrar_el_tutorial(cliente_de, alumno):
    """Se marca al mostrarlo: no hace falta (ni existe) una dirección para avisar que lo cerró."""
    from django.urls import NoReverseMatch

    with pytest.raises(NoReverseMatch):
        reverse("nucleo:tutorial_visto")
    assert "data-visto-url" not in inicio(cliente_de(alumno))


# ===================================================================== La pantalla «Ayuda»


def test_la_ayuda_resume_el_sistema_para_cada_rol(cliente_de, alumno, docente, admin, direccion):
    for persona, rol in ((alumno, Rol.ALUMNO), (docente, Rol.DOCENTE), (admin, Rol.ADMIN), (direccion, Rol.DIRECCION)):
        r = cliente_de(persona).get(reverse("nucleo:ayuda"))
        html = r.content.decode()
        assert r.status_code == 200 and "¿Qué es el aula virtual?" in html and "Para qué sirve cada parte" in html, rol
        assert ayuda.PUEDES[rol][:40] in html and "Repetir tutorial" in html and "?tutorial=1" in html, rol
        for paso in ayuda.PASOS[rol][1:-1]:  # menos la bienvenida y el cierre
            assert paso.titulo in html and paso.texto[:30] in html, (rol, paso.titulo)


def test_las_preguntas_frecuentes_son_de_cada_rol(cliente_de, alumno, docente, admin, direccion):
    assert "No puedo entrar" in cliente_de(alumno).get(reverse("nucleo:ayuda")).content.decode()
    assert "¿Cómo invito a mis alumnos?" in cliente_de(docente).get(reverse("nucleo:ayuda")).content.decode()
    assert "¿Eliminar o desactivar?" in cliente_de(admin).get(reverse("nucleo:ayuda")).content.decode()
    assert "Preguntas frecuentes" not in cliente_de(direccion).get(reverse("nucleo:ayuda")).content.decode()


def test_la_ayuda_muestra_el_contacto_del_cetpro_si_esta_configurado(cliente_de, alumno):
    from apps.nucleo import ajustes

    assert "Escribir por WhatsApp" not in cliente_de(alumno).get(reverse("nucleo:ayuda")).content.decode()
    ajustes.guardar({"whatsapp": "987654321"})
    html = cliente_de(alumno).get(reverse("nucleo:ayuda")).content.decode()
    assert "¿Sigues con dudas?" in html and "Escribir por WhatsApp" in html and "wa.me/51987654321" in html


def test_la_ayuda_pide_sesion(client):
    r = client.get(reverse("nucleo:ayuda"))
    assert r.status_code == 302 and reverse("cuentas:login") in r["Location"]


def test_los_botones_para_repetir_el_tutorial_estan_en_mi_cuenta_y_en_el_menu_lateral(cliente_de, alumno):
    html = cliente_de(alumno).get(reverse("cuentas:cuenta")).content.decode()
    assert "Ayuda y tutorial" in html and "Repetir tutorial" in html and "Ver el resumen del sistema" in html
    assert f'href="{reverse("nucleo:ayuda")}"' in html  # también el enlace «Ayuda» del menú lateral


# ===================================================================== Que lo escrito sea verdad


def textos_de_la_ayuda():
    for pasos in ayuda.PASOS.values():
        for p in pasos:
            yield p.texto
    yield from ayuda.PUEDES.values()
    for preguntas in ayuda.PREGUNTAS.values():
        for _, respuesta in preguntas:
            yield respuesta


def test_los_nombres_de_botones_que_cita_la_ayuda_existen_en_el_aula():
    """Si se cambia el nombre de un botón del aula y la ayuda sigue diciendo el viejo, esta prueba lo avisa."""
    donde = "".join(p.read_text(encoding="utf-8") for p in (RAIZ / "templates").rglob("*.html"))
    donde += (RAIZ / "apps" / "nucleo" / "menu.py").read_text(encoding="utf-8")
    citados = {c for texto in textos_de_la_ayuda() for c in re.findall(r"«([^»]+)»", texto)}
    assert len(citados) > 20
    faltan = sorted(c for c in citados if c not in donde)
    assert not faltan, f"La ayuda cita botones que ya no existen en el aula: {faltan}"


def test_ninguna_plantilla_tiene_comentarios_de_varias_lineas_con_llaves_y_numeral():
    """«{# … #}» solo vale en una línea; en varias, el texto sale escrito en la página (y puede romper el HTML)."""
    malas = [
        f"{p.relative_to(RAIZ)}:{n}"
        for p in (RAIZ / "templates").rglob("*.html")
        for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if "{#" in linea and "#}" not in linea
    ]
    assert not malas, f"Comentarios de plantilla que no cierran en la misma línea (usar {{% comment %}}): {malas}"
