"""El panel técnico de Django funciona con el usuario propio (DNI/correo)."""

import pytest
from django.urls import reverse

from apps.cuentas.models import Rol, Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def superusuario(client):
    u = Usuario.objects.create_superuser(correo="admin@cetpro.com", nombres="Admin", password="clave-admin-1")
    client.force_login(u)
    return u


def test_lista_y_formulario_de_alta(client, superusuario):
    assert client.get(reverse("admin:cuentas_usuario_changelist")).status_code == 200
    assert client.get(reverse("admin:cuentas_usuario_add")).status_code == 200


def test_crear_cuenta_desde_el_panel(client, superusuario):
    r = client.post(
        reverse("admin:cuentas_usuario_add"),
        {
            "correo": "ana@cetpro.com",
            "nombres": "Ana",
            "rol": Rol.DOCENTE,
            "password1": "una-clave-larga-9",
            "password2": "una-clave-larga-9",
        },
    )
    assert r.status_code == 302
    assert Usuario.objects.get(correo="ana@cetpro.com").rol == Rol.DOCENTE


def test_abrir_cuenta_existente(client, superusuario):
    r = client.get(reverse("admin:cuentas_usuario_change", args=[superusuario.pk]))
    assert r.status_code == 200
