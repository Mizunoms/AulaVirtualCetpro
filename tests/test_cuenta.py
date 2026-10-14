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


# ===================================================================== «Más tarde»: seguir sin cerrar la sesión


@pytest.fixture
def con_clave_temporal(alumno):
    alumno.debe_cambiar_clave = True
    alumno.save()
    return alumno


def test_la_pantalla_de_clave_nueva_es_simple_y_tiene_mas_tarde(cliente_de, con_clave_temporal):
    html = cliente_de(con_clave_temporal).get(reverse("cuentas:nueva_clave")).content.decode()
    assert "Crea tu contraseña nueva" in html and "La contraseña que te dieron es temporal" in html
    assert "3. Crear mi nueva contraseña" in html and "Más tarde" in html and "Mostrar lo que escribo" in html
    assert "Tu sesión no se cierra" in html and "Salir y hacerlo después" not in html
    assert "data-ver-claves" in html and "data-coinciden" in html


def test_mas_tarde_deja_entrar_sin_cerrar_la_sesion(cliente_de, con_clave_temporal):
    c = cliente_de(con_clave_temporal)
    assert c.get(reverse("nucleo:inicio"))["Location"] == reverse("cuentas:nueva_clave")
    r = c.post(reverse("cuentas:nueva_clave"), {"despues": "1"})
    assert r["Location"] == reverse("nucleo:inicio")
    html = c.get(reverse("nucleo:inicio")).content.decode()  # ya no la manda a elegir contraseña
    assert "lo haces más tarde" in html and "Mis notas" in html
    for ruta in (reverse("cuentas:cuenta"), reverse("academico:modulos"), reverse("nucleo:ayuda")):
        assert c.get(ruta).status_code == 200
    # La sesión sigue abierta y la contraseña temporal sigue pendiente de cambiar
    con_clave_temporal.refresh_from_db()
    assert con_clave_temporal.debe_cambiar_clave and con_clave_temporal.check_password(CLAVE)


def test_despues_de_mas_tarde_queda_el_boton_para_crear_la_contrasena_en_todas_las_pantallas(cliente_de, con_clave_temporal):
    c = cliente_de(con_clave_temporal)
    c.post(reverse("cuentas:nueva_clave"), {"despues": "1"})
    for ruta in (reverse("nucleo:inicio"), reverse("cuentas:cuenta"), reverse("academico:modulos")):
        html = c.get(ruta).content.decode()
        assert "Tu contraseña es <b>temporal</b>" in html and "Crear mi nueva contraseña" in html, ruta
        assert f'href="{reverse("cuentas:nueva_clave")}"' in html, ruta
    # En su propia pantalla no se repite el aviso
    assert "Tu contraseña es <b>temporal</b>" not in c.get(reverse("cuentas:nueva_clave")).content.decode()


def test_se_puede_crear_la_contrasena_despues_de_haber_tocado_mas_tarde(cliente_de, con_clave_temporal):
    c = cliente_de(con_clave_temporal)
    c.post(reverse("cuentas:nueva_clave"), {"despues": "1"})
    r = c.post(reverse("cuentas:nueva_clave"), {"nueva": "mi-clave-propia", "repetir": "mi-clave-propia"})
    assert r["Location"] == reverse("nucleo:inicio")
    con_clave_temporal.refresh_from_db()
    assert con_clave_temporal.check_password("mi-clave-propia") and not con_clave_temporal.debe_cambiar_clave
    assert "Tu contraseña es <b>temporal</b>" not in c.get(reverse("nucleo:inicio")).content.decode()  # ya no hay aviso


def test_el_aviso_no_sale_a_quien_ya_tiene_su_contrasena(cliente_de, alumno):
    assert "Tu contraseña es <b>temporal</b>" not in cliente_de(alumno).get(reverse("nucleo:inicio")).content.decode()


def test_mas_tarde_vale_solo_para_esta_sesion(cliente_de, con_clave_temporal, client):
    cliente_de(con_clave_temporal).post(reverse("cuentas:nueva_clave"), {"despues": "1"})
    # Cierra la sesión y vuelve a entrar con la misma contraseña temporal: otra vez se la piden
    nuevo = client
    nuevo.post(reverse("cuentas:login"), {"usuario": con_clave_temporal.dni, "clave": CLAVE, "tipo": "alumno"})
    assert nuevo.get(reverse("nucleo:inicio"))["Location"] == reverse("cuentas:nueva_clave")


def test_mas_tarde_sin_clave_temporal_no_hace_nada(cliente_de, alumno, client):
    c = cliente_de(alumno)
    r = c.post(reverse("cuentas:nueva_clave"), {"despues": "1"})
    assert r["Location"] == reverse("cuentas:cuenta") and "_clave_despues" not in c.session
    r = client.post(reverse("cuentas:nueva_clave"), {"despues": "1"})  # sin sesión
    assert r.status_code == 302 and reverse("cuentas:login") in r["Location"]


def test_las_contrasenas_vacias_no_se_aceptan_aunque_se_toque_crear(cliente_de, con_clave_temporal):
    c = cliente_de(con_clave_temporal)
    r = c.post(reverse("cuentas:nueva_clave"), {"nueva": "", "repetir": ""})
    assert "al menos 6" in c.get(r["Location"]).content.decode()
    con_clave_temporal.refresh_from_db()
    assert con_clave_temporal.debe_cambiar_clave
