"""Ajustes del aula (solo administrador): colores, textos, logo y registro de actividad."""

import base64

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.nucleo import ajustes, archivos, color
from apps.nucleo.models import Registro

pytestmark = pytest.mark.django_db
AJUSTES = "nucleo:ajustes"

# PNG de 1x1 píxel
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def test_solo_el_administrador_ve_los_ajustes(cliente_de, alumno, docente, admin, client):
    assert client.get(reverse(AJUSTES)).status_code == 302
    for persona in (alumno, docente):
        r = cliente_de(persona).get(reverse(AJUSTES))
        assert r.status_code == 403 and "No tienes permiso" in r.content.decode()
    assert cliente_de(admin).get(reverse(AJUSTES)).status_code == 200


def test_pestanas_de_ajustes(cliente_de, admin):
    c = cliente_de(admin)
    assert "Nombres y colores" in c.get(reverse(AJUSTES)).content.decode()
    assert "Periodo académico activo" in c.get(reverse(AJUSTES) + "?tab=periodo").content.decode()
    assert "WhatsApp de soporte" in c.get(reverse(AJUSTES) + "?tab=contacto").content.decode()
    assert "Nombres y colores" in c.get(reverse(AJUSTES) + "?tab=rara").content.decode()


def test_guardar_identidad_cambia_el_aspecto_de_todo(cliente_de, admin, alumno):
    c = cliente_de(admin)
    r = c.post(
        reverse(AJUSTES),
        {
            "tab": "identidad",
            "centro_nombre": "CETPRO Nuevo",
            "aula_nombre": "Mi Aula",
            "bienvenida": "Hola a todos",
            "color_principal": "#112233",
            "color_acento": "#aa0000",
            "color_secundario": "#0a4aa0",
        },
    )
    assert r["Location"] == reverse(AJUSTES) + "?tab=identidad"
    assert ajustes.ajuste("centro_nombre") == "CETPRO Nuevo" and ajustes.ajuste("color_acento") == "#AA0000"
    html = cliente_de(alumno).get(reverse("nucleo:inicio")).content.decode()
    assert "Mi Aula" in html and "--navy:#112233" in html and "--rojo:#AA0000" in html
    assert Registro.objects.filter(accion="ajustes", usuario=admin).exists()


@pytest.mark.parametrize(
    ("cambio", "texto"),
    [
        ({"centro_nombre": ""}, "Escribe el nombre del centro"),
        ({"color_principal": "azul"}, "El color principal no es válido"),
        ({"color_acento": "#FFFF00"}, "El color de acento es muy claro"),
    ],
)
def test_ajustes_identidad_con_errores(cliente_de, admin, cambio, texto):
    datos = {
        "tab": "identidad", "centro_nombre": "X", "aula_nombre": "Y", "bienvenida": "",
        "color_principal": "#112233", "color_acento": "#aa0000", "color_secundario": "#0a4aa0",
    }  # fmt: skip
    c = cliente_de(admin)
    r = c.post(reverse(AJUSTES), {**datos, **cambio})
    assert texto in c.get(r["Location"]).content.decode()
    assert ajustes.ajuste("centro_nombre") == "CETPRO Mangomarca"  # nada se guardó


def test_restaurar_colores(cliente_de, admin):
    ajustes.guardar({"color_principal": "#112233"})
    cliente_de(admin).post(reverse(AJUSTES), {"tab": "identidad", "restaurar_colores": "1"})
    assert ajustes.ajuste("color_principal") == "#0B1B35"


def test_periodo_y_dominio(cliente_de, admin):
    c = cliente_de(admin)
    c.post(
        reverse(AJUSTES),
        {"tab": "periodo", "periodo": "2027-I", "dominio_correo": "@Colegio.edu.pe", "aviso_general": "Feriado el lunes"},
    )
    assert ajustes.ajuste("periodo") == "2027-I" and ajustes.ajuste("dominio_correo") == "colegio.edu.pe"
    assert ajustes.ajuste("registro_abierto") == "0"  # la casilla no se marcó
    html = c.get(reverse("nucleo:inicio")).content.decode()
    assert "Feriado el lunes" in html  # aviso general arriba, para todos
    r = c.post(reverse(AJUSTES), {"tab": "periodo", "dominio_correo": "sinpunto"})
    assert "dominio del correo" in c.get(r["Location"]).content.decode()


def test_contacto_limpia_telefonos_y_pide_https(cliente_de, admin):
    c = cliente_de(admin)
    c.post(
        reverse(AJUSTES),
        {"tab": "contacto", "whatsapp": "987 654-321", "telefono": "01 123x4567", "web": "https://cetpro.edu.pe"},
    )
    assert ajustes.ajuste("whatsapp") == "987654321" and ajustes.ajuste("telefono") == "01 1234567"
    r = c.post(reverse(AJUSTES), {"tab": "contacto", "web": "ftp://x"})
    assert "debe empezar con https://" in c.get(r["Location"]).content.decode()


def test_ayuda_aparece_en_la_pantalla_de_entrada(client, cliente_de, admin):
    ajustes.guardar({"whatsapp": "987654321", "telefono": "01 1234567", "horario_atencion": "Lunes a viernes"})
    html = client.get(reverse("cuentas:login")).content.decode()
    assert "https://wa.me/51987654321" in html and "Llamar: 01 1234567" in html and "Lunes a viernes" in html


def test_subir_y_quitar_el_logo(cliente_de, admin, client):
    c = cliente_de(admin)
    foto = SimpleUploadedFile("mi logo.png", PNG, content_type="image/png")
    r = c.post(reverse("nucleo:ajustes_imagen"), {"cual": "logo", "imagen": foto})
    assert r.status_code == 302
    ruta = ajustes.ajuste("logo")
    assert ruta.endswith(".png") and (archivos._base() / ruta).is_file()
    # El logo se ve sin haber entrado (pantalla de entrada)
    r = client.get(reverse("nucleo:marca_logo"))
    assert r.status_code == 200 and b"".join(r.streaming_content).startswith(b"\x89PNG")
    assert "/marca/logo?v=" in client.get(reverse("cuentas:login")).content.decode()
    c.post(reverse("nucleo:ajustes_imagen"), {"cual": "logo", "quitar": "1"})
    assert ajustes.ajuste("logo") == "" and not (archivos._base() / ruta).exists()
    assert client.get(reverse("nucleo:marca_logo")).status_code == 404


@pytest.mark.parametrize(
    ("nombre", "contenido", "texto"),
    [
        ("logo.exe", b"MZ....", "no está permitido"),
        ("logo.png", b"esto no es un png", "no parece ser lo que dice"),
        ("logo.pdf", b"%PDF-1.4 hola", "Sube una imagen"),
    ],
)
def test_logo_rechaza_archivos_raros(cliente_de, admin, nombre, contenido, texto):
    c = cliente_de(admin)
    r = c.post(reverse("nucleo:ajustes_imagen"), {"cual": "logo", "imagen": SimpleUploadedFile(nombre, contenido)})
    assert texto in c.get(r["Location"].split("#")[0]).content.decode()
    assert ajustes.ajuste("logo") == ""
    assert not any((archivos._base()).rglob("*.*")) if archivos._base().exists() else True


def test_foto_de_taller(cliente_de, admin, client):
    c = cliente_de(admin)
    c.post(reverse("nucleo:ajustes_foto"), {"nombre": "Soporte Técnico", "foto": SimpleUploadedFile("t.png", PNG)})
    soporte = next(e for e in ajustes.especialidades() if e["nombre"] == "Soporte Técnico")
    assert soporte["foto"].endswith(".png")
    assert client.get(reverse("nucleo:marca_especialidad") + "?n=Soporte Técnico").status_code == 200
    assert client.get(reverse("nucleo:marca_especialidad") + "?n=Otra").status_code == 404
    assert c.post(reverse("nucleo:ajustes_foto"), {"nombre": "No existe"}).status_code == 404


def test_registro_de_actividad(cliente_de, admin, alumno, docente):
    Registro.anotar(admin, "cuenta", "Ana creó la cuenta de Rosa.")
    Registro.anotar(None, "acceso", "Alguien entró.")
    c = cliente_de(admin)
    html = c.get(reverse("nucleo:registro")).content.decode()
    assert "Ana creó la cuenta de Rosa." in html and "Alguien entró." in html and "no guarda contraseñas" in html
    html = c.get(reverse("nucleo:registro") + "?accion=cuenta").content.decode()
    assert "Ana creó la cuenta de Rosa." in html and "Alguien entró." not in html
    assert cliente_de(docente).get(reverse("nucleo:registro")).status_code == 403


def test_registro_se_pagina(cliente_de, admin):
    for i in range(30):
        Registro.anotar(admin, "ajustes", f"Cambio número {i}")
    html = cliente_de(admin).get(reverse("nucleo:registro")).content.decode()
    assert "Mostrando 1–25 de 30 movimientos" in html and "Siguiente ›" in html
    html = cliente_de(admin).get(reverse("nucleo:registro") + "?pagina=2").content.decode()
    assert "Mostrando 26–30" in html


def test_colores_y_contraste():
    assert color.valido("#0B1B35") and not color.valido("0B1B35") and not color.valido("#12")
    assert color.mezclar("#000000", "#FFFFFF", 0.5) == "#808080"
    assert color.contraste("#000000", "#FFFFFF") == pytest.approx(21)
    assert color.contraste("#FFFF00", "#FFFFFF") < 4.5 < color.contraste("#1249A3", "#FFFFFF")


def test_paginas_de_error_con_el_marco_del_aula(client):
    r = client.get("/no-existe-esta-pagina")
    assert r.status_code == 404 and "No encontramos lo que buscas." in r.content.decode()
