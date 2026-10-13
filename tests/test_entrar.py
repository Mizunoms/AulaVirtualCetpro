"""Entrar al aula con DNI (alumnos) o correo (docentes y administración)."""

import pytest
from django.urls import reverse

from apps.cuentas.backends import normalizar_identificador
from apps.cuentas.models import Rol, Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def alumno():
    return Usuario.objects.create_user(
        dni="12345678", nombres="Rosa", apellidos="Quispe Mamani", password="clave-segura-1", rol=Rol.ALUMNO
    )


@pytest.fixture
def docente():
    return Usuario.objects.create_user(
        correo="maria@cetpro.com",
        nombres="María",
        apellidos="Torres",
        password="otra-clave-2",
        rol=Rol.DOCENTE,
    )


def test_identificador_dni_correo_y_atajo():
    assert normalizar_identificador("12345678") == ("dni", "12345678")
    assert normalizar_identificador(" Maria@Cetpro.com ") == ("correo", "maria@cetpro.com")
    assert normalizar_identificador("maria") == ("correo", "maria@cetpro.com")


def test_inicio_pide_entrar(client):
    r = client.get(reverse("nucleo:inicio"))
    assert r.status_code == 302
    assert reverse("cuentas:entrar") in r["Location"]


def test_alumno_entra_con_dni(client, alumno):
    r = client.post(reverse("cuentas:entrar"), {"username": "12345678", "password": "clave-segura-1"})
    assert r.status_code == 302
    r = client.get(reverse("nucleo:inicio"))
    assert r.status_code == 200
    assert "Rosa" in r.content.decode()


def test_docente_entra_con_correo_y_con_atajo(client, docente):
    for usuario in ("maria@cetpro.com", "maria"):
        client.logout()
        r = client.post(reverse("cuentas:entrar"), {"username": usuario, "password": "otra-clave-2"})
        assert r.status_code == 302, usuario


def test_clave_mala_no_entra(client, alumno):
    r = client.post(reverse("cuentas:entrar"), {"username": "12345678", "password": "mala"})
    assert r.status_code == 200
    assert "no son correctos" in r.content.decode()


def test_cuenta_desactivada_no_entra(client, alumno):
    alumno.is_active = False
    alumno.save()
    r = client.post(reverse("cuentas:entrar"), {"username": "12345678", "password": "clave-segura-1"})
    assert r.status_code == 200
    assert "no son correctos" in r.content.decode()


def test_alumno_sin_clave_no_puede_entrar(client):
    """Alumno cargado desde una lista que todavía no creó su contraseña."""
    Usuario.objects.create_user(dni="87654321", nombres="Luis", password=None)
    r = client.post(reverse("cuentas:entrar"), {"username": "87654321", "password": ""})
    assert r.status_code == 200


def test_salir_solo_por_post(client, alumno):
    client.force_login(alumno)
    assert client.get(reverse("cuentas:salir")).status_code == 405
    r = client.post(reverse("cuentas:salir"))
    assert r.status_code == 302
    assert client.get(reverse("nucleo:inicio")).status_code == 302
