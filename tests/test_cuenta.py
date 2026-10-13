"""Mi cuenta: preferencias de accesibilidad, tema, cambio de contraseña y contraseña temporal."""

import pytest
from django.urls import reverse

from apps.cuentas.models import Preferencia
from apps.nucleo.models import Registro

from .conftest import CLAVE

pytestmark = pytest.mark.django_db


def test_mi_cuenta_muestra_mis_datos(cliente_de, alumno):
    html = cliente_de(alumno).get(reverse("cuentas:cuenta")).content.decode()
    assert "Rosa Quispe Mamani" in html and "DNI 12345678" in html
    assert "Tamaño de la letra" in html and "Cambiar mi contraseña" in html


def test_guardar_preferencias_y_se_aplican_en_todas_las_paginas(cliente_de, alumno):
    c = cliente_de(alumno)
    r = c.post(
        reverse("cuentas:preferencias"),
        {"tamano_letra": "muy_grande", "alto_contraste": "1", "lectura_voz": "1", "tema": "oscuro"},
    )
    assert r.status_code == 302
    p = Preferencia.objects.get(usuario=alumno)
    assert (p.tamano_letra, p.alto_contraste, p.lectura_voz) == ("muy_grande", True, True)
    assert r.cookies["aula_tema"].value == "oscuro"
    html = c.get(reverse("cuentas:cuenta")).content.decode()
    assert 'class="letra-muy_grande"' in html and 'data-tema="oscuro"' in html
    assert '<body class="alto-contraste voz">' in html


def test_preferencia_invalida_vuelve_a_normal(cliente_de, alumno):
    c = cliente_de(alumno)
    c.post(reverse("cuentas:preferencias"), {"tamano_letra": "gigante"})
    assert Preferencia.objects.get(usuario=alumno).tamano_letra == "normal"


def test_tema_se_cambia_tambien_sin_sesion(client):
    r = client.post(reverse("nucleo:tema"), {"tema": "oscuro", "volver": "/login?como=personal"})
    assert r["Location"] == "/login?como=personal" and r.cookies["aula_tema"].value == "oscuro"
    assert 'data-tema="oscuro"' in client.get(reverse("cuentas:login")).content.decode()


@pytest.mark.parametrize("volver", ["https://malo.com", "//malo.com", "/tema", "javascript:alert(1)"])
def test_tema_nunca_vuelve_a_otro_sitio(client, volver):
    assert client.post(reverse("nucleo:tema"), {"tema": "claro", "volver": volver})["Location"] == "/"


def test_cambiar_contrasena(cliente_de, alumno, client):
    c = cliente_de(alumno)
    r = c.post(reverse("cuentas:clave"), {"actual": CLAVE, "nueva": "nueva-mas-larga", "repetir": "nueva-mas-larga"})
    assert r["Location"] == reverse("cuentas:cuenta")
    alumno.refresh_from_db()
    assert alumno.check_password("nueva-mas-larga")
    assert c.get(reverse("cuentas:cuenta")).status_code == 200  # la sesión sigue abierta
    assert Registro.objects.filter(accion="clave", detalle__contains="cambió su propia contraseña").exists()


@pytest.mark.parametrize(
    ("datos", "texto"),
    [
        ({"actual": "mala", "nueva": "abcdefg", "repetir": "abcdefg"}, "contraseña actual no es correcta"),
        ({"actual": CLAVE, "nueva": "corta", "repetir": "corta"}, "al menos 6"),
        ({"actual": CLAVE, "nueva": "abcdefg", "repetir": "otraotra"}, "no son iguales"),
    ],
)
def test_cambiar_contrasena_con_errores(cliente_de, alumno, datos, texto):
    c = cliente_de(alumno)
    r = c.post(reverse("cuentas:clave"), datos)
    assert texto in c.get(r["Location"].split("#")[0]).content.decode()
    alumno.refresh_from_db()
    assert alumno.check_password(CLAVE)


def test_contrasena_temporal_obliga_a_elegir_la_propia(cliente_de, alumno):
    alumno.debe_cambiar_clave = True
    alumno.save()
    c = cliente_de(alumno)
    assert c.get(reverse("nucleo:inicio"))["Location"] == reverse("cuentas:nueva_clave")
    assert c.get(reverse("cuentas:cuenta"))["Location"] == reverse("cuentas:nueva_clave")
    html = c.get(reverse("cuentas:nueva_clave")).content.decode()
    assert "La contraseña que te dieron es temporal" in html
    # No vale dejar la misma ni el DNI
    for mala in (CLAVE, "12345678"):
        r = c.post(reverse("cuentas:nueva_clave"), {"nueva": mala, "repetir": mala})
        assert "distinta de la que te dieron" in c.get(r["Location"]).content.decode()
    r = c.post(reverse("cuentas:nueva_clave"), {"nueva": "mi-clave-propia", "repetir": "mi-clave-propia"})
    assert r["Location"] == reverse("nucleo:inicio")
    alumno.refresh_from_db()
    assert alumno.check_password("mi-clave-propia") and not alumno.debe_cambiar_clave
    assert c.get(reverse("nucleo:inicio")).status_code == 200


def test_sin_clave_temporal_no_se_cambia_por_nueva_clave(cliente_de, alumno):
    c = cliente_de(alumno)
    assert c.get(reverse("cuentas:nueva_clave"))["Location"] == reverse("cuentas:cuenta")
    r = c.post(reverse("cuentas:nueva_clave"), {"nueva": "otra-clave-9", "repetir": "otra-clave-9"})
    assert r["Location"] == reverse("cuentas:cuenta")
    alumno.refresh_from_db()
    assert alumno.check_password(CLAVE)


def test_menu_segun_el_rol(cliente_de, alumno, docente, admin):
    assert "Mis notas" in cliente_de(alumno).get(reverse("nucleo:inicio")).content.decode()
    html = cliente_de(docente).get(reverse("nucleo:inicio")).content.decode()
    assert "Por calificar" in html and "Mis notas" not in html
    html = cliente_de(admin).get(reverse("nucleo:inicio")).content.decode()
    assert "Personas" in html and "Ajustes" in html
