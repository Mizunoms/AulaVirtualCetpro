"""«Crear mi cuenta»: el alumno con su DNI (en lista o nuevo con el código del módulo)."""

from datetime import date

import pytest
from django.urls import reverse

from apps.academico.models import Modulo
from apps.cuentas.models import Preferencia, Rol, Usuario
from apps.nucleo import ajustes

from .conftest import CLAVE

pytestmark = pytest.mark.django_db


@pytest.fixture
def modulo(docente):
    return Modulo.crear(
        nombre="Soporte – Módulo 1",
        especialidad="Soporte Técnico",
        modulo="Módulo 1",
        periodo="2026-II",
        turno="noche",
        docente=docente,
    )


def paso1(client, dni):
    return client.post(reverse("cuentas:registro"), {"dni": dni})


# ---------- Paso 1 ----------


def test_pantalla_inicial(client):
    html = client.get(reverse("cuentas:registro")).content.decode()
    assert "Paso 1 de 3" in html and "Tu DNI" in html and "Entrar con mi DNI y contraseña" in html


def test_dni_con_numeros_de_menos(client):
    r = paso1(client, "123")
    assert r["Location"] == reverse("cuentas:registro")
    html = client.get(r["Location"]).content.decode()
    assert "El DNI tiene 8 números" in html and 'value="123"' in html


def test_dni_que_ya_tiene_cuenta_va_a_entrar(client, alumno):
    r = paso1(client, "12345678")
    assert r["Location"] == reverse("cuentas:login")
    html = client.get(r["Location"]).content.decode()
    assert "Ya tienes tu cuenta" in html and 'value="12345678"' in html


def test_dni_de_docente_no_crea_cuenta(client, db):
    Usuario.objects.create_user(dni="70000000", nombres="Prof", rol=Rol.DOCENTE, password=None)  # sin contraseña todavía
    r = paso1(client, "70000000")
    assert "no se puede crear una cuenta aquí" in client.get(r["Location"]).content.decode()


def test_dni_nuevo_con_matriculas_cerradas(client, db):
    ajustes.guardar({"registro_abierto": "0"})
    html = client.get(reverse("cuentas:registro")).content.decode()
    assert "Solo pueden crear su cuenta los alumnos que el CETPRO ya registró" in html
    r = paso1(client, "40000000")
    assert "no está en la lista del CETPRO" in client.get(r["Location"]).content.decode()


def test_muchos_dni_desde_la_misma_red(client, db):
    for _ in range(60):
        paso1(client, "1234")  # los que tienen menos de 8 números no cuentan
    for i in range(60):
        paso1(client, f"4000{i:04d}")
    r = paso1(client, "40009999")
    assert "Se revisaron muchos DNI desde esta red" in client.get(r["Location"]).content.decode()


# ---------- Alumno nuevo con el código del módulo ----------


def datos_nuevo(modulo, **cambios):
    return {
        "codigo": modulo.codigo_fmt, "nombres": "rosa maría", "apellidos": "paredes quispe",
        "telefono": "987 654 321", "fecha_nacimiento": "1990-05-17", **cambios,
    }  # fmt: skip


def test_alumno_nuevo_crea_su_cuenta(client, modulo):
    r = paso1(client, "40111222")
    assert r["Location"] == reverse("cuentas:registro_datos")
    assert "Paso 2 de 3" in client.get(r["Location"]).content.decode()
    r = client.post(reverse("cuentas:registro_datos"), datos_nuevo(modulo, letra_grande="1"))
    assert r["Location"] == reverse("cuentas:nueva_clave")
    u = Usuario.objects.get(dni="40111222")
    assert (u.nombres, u.apellidos, u.telefono, u.fecha_nacimiento) == (
        "Rosa María",
        "Paredes Quispe",
        "987654321",
        date(1990, 5, 17),
    )
    assert u.rol == Rol.ALUMNO and u.origen == "registro" and u.debe_cambiar_clave and not u.pendiente
    assert modulo.es_alumno(u) and Preferencia.objects.get(usuario=u).tamano_letra == "grande"
    # Ya tiene sesión y ve su contraseña temporal para elegir la suya (paso 3)
    html = client.get(reverse("cuentas:nueva_clave")).content.decode()
    assert "¡Tu cuenta está lista, Rosa!" in html and "Paso 3 de 3" in html and "Contraseña temporal" in html
    temporal = html.split('id="clave-nueva">')[1].split("<")[0]
    assert u.check_password(temporal)
    r = client.post(reverse("cuentas:nueva_clave"), {"nueva": "mi-clave-nueva", "repetir": "mi-clave-nueva"})
    assert r["Location"] == reverse("nucleo:inicio")
    assert client.get(reverse("nucleo:inicio")).status_code == 200


@pytest.mark.parametrize(
    ("cambio", "texto"),
    [
        ({"nombres": "R0sa"}, "Escribe tus nombres y tus apellidos"),
        ({"apellidos": ""}, "Escribe tus nombres y tus apellidos"),
        ({"telefono": "12345"}, "El celular tiene 9 números"),
        ({"fecha_nacimiento": "2030-01-01"}, "Revisa tu fecha de nacimiento"),
        ({"fecha_nacimiento": "1900-01-01"}, "Revisa tu fecha de nacimiento"),
        ({"codigo": "XYZ0000"}, "Ese código no es correcto"),
    ],
)
def test_datos_con_errores_no_crean_la_cuenta(client, modulo, cambio, texto):
    paso1(client, "40111222")
    r = client.post(reverse("cuentas:registro_datos"), datos_nuevo(modulo, **cambio))
    assert r["Location"] == reverse("cuentas:registro_datos")
    html = client.get(r["Location"]).content.decode()
    assert texto in html and "Paso 2 de 3" in html
    assert not Usuario.objects.filter(dni="40111222").exists()


def test_los_datos_escritos_se_conservan_al_equivocarse(client, modulo):
    paso1(client, "40111222")
    r = client.post(reverse("cuentas:registro_datos"), datos_nuevo(modulo, telefono="123"))
    html = client.get(r["Location"]).content.decode()
    assert 'value="rosa maría"' in html and 'value="paredes quispe"' in html


def test_modulo_sin_inscripcion_abierta(client, modulo):
    modulo.inscripcion_abierta = False
    modulo.save()
    paso1(client, "40111222")
    r = client.post(reverse("cuentas:registro_datos"), datos_nuevo(modulo))
    assert "ya no acepta alumnos nuevos" in client.get(r["Location"]).content.decode()


def test_muchos_codigos_equivocados(client, modulo):
    paso1(client, "40111222")
    for _ in range(15):
        client.post(reverse("cuentas:registro_datos"), datos_nuevo(modulo, codigo="ZZZ9999"))
    r = client.post(reverse("cuentas:registro_datos"), datos_nuevo(modulo))
    assert "Hubo muchos códigos equivocados" in client.get(r["Location"]).content.decode()


def test_sin_el_paso_1_no_se_puede_saltar_al_2(client, modulo):
    for ruta in ("cuentas:registro_datos", "cuentas:registro_confirmar"):
        r = client.get(reverse(ruta))
        assert r["Location"] == reverse("cuentas:registro")
        assert "Empieza escribiendo tu DNI" in client.get(r["Location"]).content.decode()
    r = client.post(reverse("cuentas:registro_datos"), datos_nuevo(modulo))
    assert r["Location"] == reverse("cuentas:registro") and not Usuario.objects.filter(dni="40111222").exists()


def test_el_registro_vence_a_los_30_minutos(client, modulo):
    paso1(client, "40111222")
    s = client.session
    s["_registro"] = {**s["_registro"], "t": s["_registro"]["t"] - 1900}
    s.save()
    r = client.post(reverse("cuentas:registro_datos"), datos_nuevo(modulo))
    assert r["Location"] == reverse("cuentas:registro") and not Usuario.objects.filter(dni="40111222").exists()


def test_un_alumno_con_sesion_no_ve_el_registro(cliente_de, alumno):
    assert cliente_de(alumno).get(reverse("cuentas:registro"))["Location"] == reverse("nucleo:inicio")


# ---------- Alumno ya cargado en una lista ----------


def en_lista(modulo, nacimiento=date(1995, 3, 2)):
    u = Usuario.objects.crear_alumno("45678912", "Ana María", "Quispe Rojas", fecha_nacimiento=nacimiento)
    modulo.matricular(u)
    return u


def test_alumno_en_lista_confirma_con_su_fecha(client, modulo):
    u = en_lista(modulo)
    r = paso1(client, "45678912")
    assert r["Location"] == reverse("cuentas:registro_confirmar")
    html = client.get(r["Location"]).content.decode()
    assert "¿Eres Ana Q.?" in html and "Soporte – Módulo 1" in html and "Para confirmar, escribe tu fecha de nacimiento" in html
    r = client.post(reverse("cuentas:registro_confirmar"), {"fecha_nacimiento": "1995-03-02", "telefono": "987654321"})
    assert r["Location"] == reverse("cuentas:nueva_clave")
    u.refresh_from_db()
    assert not u.pendiente and u.debe_cambiar_clave and u.telefono == "987654321" and u.activado
    assert client.get(reverse("cuentas:nueva_clave")).status_code == 200


def test_fecha_equivocada_no_deja_pasar_y_se_limita(client, modulo):
    u = en_lista(modulo)
    paso1(client, "45678912")
    r = client.post(reverse("cuentas:registro_confirmar"), {"fecha_nacimiento": "1990-01-01"})
    assert "no coincide con la que tiene el CETPRO" in client.get(r["Location"]).content.decode()
    for _ in range(4):
        client.post(reverse("cuentas:registro_confirmar"), {"fecha_nacimiento": "1990-01-01"})
    r = client.post(reverse("cuentas:registro_confirmar"), {"fecha_nacimiento": "1995-03-02"})  # ni la buena
    assert "Hubo muchos intentos" in client.get(r["Location"]).content.decode()
    u.refresh_from_db()
    assert u.pendiente


def test_alumno_en_lista_sin_fecha_no_la_pide(client, modulo):
    en_lista(modulo, nacimiento=None)
    paso1(client, "45678912")
    html = client.get(reverse("cuentas:registro_confirmar")).content.decode()
    assert "Para confirmar, escribe tu fecha de nacimiento" not in html
    r = client.post(reverse("cuentas:registro_confirmar"), {"telefono": ""})
    assert r["Location"] == reverse("cuentas:nueva_clave")


def test_celular_mal_escrito_al_confirmar(client, modulo):
    en_lista(modulo, nacimiento=None)
    paso1(client, "45678912")
    r = client.post(reverse("cuentas:registro_confirmar"), {"telefono": "123"})
    assert "El celular tiene 9 números" in client.get(r["Location"]).content.decode()


def test_pendiente_que_entra_por_login_va_a_crear_su_cuenta(client, modulo):
    en_lista(modulo)
    r = client.post(reverse("cuentas:login"), {"usuario": "45678912", "clave": "", "tipo": "alumno"})
    assert r["Location"] == reverse("cuentas:registro")
    assert 'value="45678912"' in client.get(r["Location"]).content.decode()


def test_cuenta_desactivada_no_puede_crearse(client, modulo):
    u = en_lista(modulo)
    u.is_active = False
    u.save()
    r = paso1(client, "45678912")
    assert "no se puede crear una cuenta aquí" in client.get(r["Location"]).content.decode()


def test_clave_temporal_de_registro_no_se_usa_para_entrar_sin_cambiarla(client, modulo):
    paso1(client, "40111222")
    client.post(reverse("cuentas:registro_datos"), datos_nuevo(modulo))
    u = Usuario.objects.get(dni="40111222")
    assert u.debe_cambiar_clave
    assert client.get(reverse("academico:modulos"))["Location"] == reverse("cuentas:nueva_clave")
    assert CLAVE  # (la clave de las pruebas no se usa aquí)
