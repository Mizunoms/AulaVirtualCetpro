"""Entrar y salir del aula: alumno con DNI, profesor con correo, límite de intentos y cuentas especiales."""

import pytest
from django.urls import reverse

from apps.cuentas.models import Rol, Usuario
from apps.nucleo import ajustes
from apps.nucleo.models import IntentoAcceso, Registro

from .conftest import CLAVE

pytestmark = pytest.mark.django_db
LOGIN = "cuentas:login"


def entrar(client, usuario, clave=CLAVE, tipo="alumno"):
    return client.post(reverse(LOGIN), {"usuario": usuario, "clave": clave, "tipo": tipo})


def test_inicio_pide_entrar_y_vuelve_despues(client, alumno):
    r = client.get(reverse("cuentas:cuenta"))
    assert r.status_code == 302 and r["Location"].endswith(reverse(LOGIN))
    r = entrar(client, "12345678")
    assert r.status_code == 302 and r["Location"] == reverse("cuentas:cuenta")  # vuelve a donde quería ir


def test_pantalla_de_entrada_tiene_las_dos_opciones(client):
    html = client.get(reverse(LOGIN)).content.decode()
    assert "Soy alumno" in html and "Soy profesor" in html and "Tu DNI" in html
    html = client.get(reverse(LOGIN) + "?como=personal").content.decode()
    assert "Tu correo del aula" in html and "@cetpro.com" in html


def test_alumno_entra_con_dni(client, alumno):
    r = entrar(client, "12345678")
    assert r.status_code == 302 and r["Location"] == reverse("nucleo:inicio")
    html = client.get(reverse("nucleo:inicio")).content.decode()
    assert "Hola, Rosa" in html
    assert Registro.objects.filter(accion="acceso", usuario=alumno).exists()


def test_profesor_entra_con_correo_o_solo_con_su_nombre(client, docente):
    for escrito in ("maria@cetpro.com", "MARIA", "Maria@Cetpro.com"):
        client.logout()
        r = entrar(client, escrito, tipo="personal")
        assert r.status_code == 302 and r["Location"] == reverse("nucleo:inicio"), escrito


def test_dominio_del_correo_se_lee_de_los_ajustes(client, docente):
    ajustes.guardar({"dominio_correo": "otro.edu.pe"})
    docente.correo = "maria@otro.edu.pe"
    docente.save()
    assert entrar(client, "maria", tipo="personal")["Location"] == reverse("nucleo:inicio")


def test_clave_mala_no_entra_y_el_mensaje_no_dice_cual_fallo(client, alumno):
    r = entrar(client, "12345678", "mala")
    assert r.status_code == 302
    html = client.get(r["Location"]).content.decode()
    assert "El DNI o la contraseña no son correctos" in html
    assert not client.get(reverse("nucleo:inicio")).status_code == 200


def test_dni_que_no_existe_da_el_mismo_mensaje(client, db):
    r = entrar(client, "99999999", "cualquiera")
    assert "El DNI o la contraseña no son correctos" in client.get(r["Location"]).content.decode()


def test_alumno_con_correo_va_a_la_opcion_de_profesor(client, alumno):
    r = entrar(client, "rosa@gmail.com", tipo="alumno")
    assert r["Location"].endswith("?como=personal")


def test_personal_sin_arroba_se_completa_y_con_error_mantiene_la_opcion(client, db):
    r = entrar(client, "nadie", "x", tipo="personal")
    assert r["Location"].endswith("?como=personal")


def test_cuenta_desactivada_no_entra(client, alumno):
    alumno.is_active = False
    alumno.save()
    r = entrar(client, "12345678")
    assert "Tu cuenta está desactivada" in client.get(r["Location"]).content.decode()


def test_alumno_en_lista_sin_clave_va_a_crear_su_cuenta(client, db):
    Usuario.objects.create_user(dni="87654321", nombres="Luis", password=None)
    r = entrar(client, "87654321", "")
    assert r["Location"] == reverse("cuentas:registro")


def test_muchos_intentos_frenan_la_cuenta_15_minutos(client, alumno):
    for _ in range(8):
        entrar(client, "12345678", "mala")
    assert IntentoAcceso.objects.filter(clave="login:12345678").count() == 8
    # Ahora ni con la clave buena entra
    r = entrar(client, "12345678")
    assert "Hubo muchos intentos" in client.get(r["Location"]).content.decode()
    assert client.get(reverse("nucleo:inicio")).status_code == 302


def test_entrar_bien_limpia_los_intentos(client, alumno):
    for _ in range(3):
        entrar(client, "12345678", "mala")
    entrar(client, "12345678")
    assert not IntentoAcceso.objects.filter(clave="login:12345678").exists()


def test_salir_solo_por_post_y_deja_la_sesion_cerrada(cliente_de, alumno):
    c = cliente_de(alumno)
    assert c.get(reverse("cuentas:salir")).status_code == 405
    r = c.post(reverse("cuentas:salir"))
    assert r.status_code == 302
    assert c.get(reverse("nucleo:inicio")).status_code == 302
    assert "Cerraste sesión" in c.get(reverse(LOGIN)).content.decode()


def test_profesor_que_sale_vuelve_a_la_opcion_de_profesor(cliente_de, docente):
    r = cliente_de(docente).post(reverse("cuentas:salir"))
    assert r["Location"].endswith("?como=personal")


def test_ya_con_sesion_entrar_lleva_al_inicio(cliente_de, alumno):
    assert cliente_de(alumno).get(reverse(LOGIN))["Location"] == reverse("nucleo:inicio")


def test_no_se_vuelve_a_paginas_de_otro_sitio(client, alumno):
    s = client.session
    s["_volver_a"] = "//malo.com/robar"
    s.save()
    assert entrar(client, "12345678")["Location"] == reverse("nucleo:inicio")


def test_roles_y_nombres(alumno, docente, admin):
    assert alumno.get_rol_display() == "Alumno" and docente.get_rol_display() == "Docente"
    assert admin.es_admin and not admin.es_alumno
    assert alumno.iniciales == "RQ" and alumno.primer_nombre == "Rosa"
    assert alumno.identificador == "DNI 12345678" and docente.identificador == "maria@cetpro.com"
    assert Rol.ADMIN.value == "admin"
