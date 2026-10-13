"""Mensajes privados entre alumno y docente de un módulo (y «mensaje a todos»)."""

from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.academico.models import Modulo
from apps.cuentas.models import Rol, Usuario
from apps.mensajes.models import Conversacion, Mensaje
from apps.nucleo import menu

from . import muestras
from .conftest import CLAVE

pytestmark = pytest.mark.django_db


@pytest.fixture
def modulo(docente):
    return Modulo.crear(
        nombre="Peluquería – M1", especialidad="Peluquería y Barbería", periodo="2026-II", turno="mañana", docente=docente
    )


@pytest.fixture
def luis(modulo):
    u = Usuario.objects.create_user(dni="40000001", nombres="Luis", apellidos="Paz", password=CLAVE, rol=Rol.ALUMNO)
    modulo.matricular(u)
    return u


@pytest.fixture
def rosa(modulo, alumno):
    modulo.matricular(alumno)
    return alumno


@pytest.fixture
def otro_docente(db):
    return Usuario.objects.create_user(
        correo="pedro@cetpro.com", nombres="Pedro", apellidos="Rojas", password=CLAVE, rol=Rol.DOCENTE
    )


@pytest.fixture
def forastero(db):
    """Un alumno que no está en el módulo."""
    return Usuario.objects.create_user(dni="40000099", nombres="Julia", apellidos="Vega", password=CLAVE, rol=Rol.ALUMNO)


def escribir(c, modulo, para, texto="Hola, profesora", **extra):
    return c.post(reverse("mensajes:nuevo"), {"curso": modulo.pk, "para": para, "texto": texto, **extra})


def conversacion(modulo, docente, alumno):
    return Conversacion.objects.get(modulo=modulo, docente=docente, alumno=alumno)


# ===================================================================== Nivel 1: tus módulos


def test_hay_que_iniciar_sesion():
    r = Client().get(reverse("mensajes:index"))
    assert r.status_code == 302 and r["Location"] == reverse("cuentas:login")


def test_admin_no_tiene_mensajes(cliente_de, admin):
    assert cliente_de(admin).get(reverse("mensajes:index")).status_code == 403


def test_alumno_ve_su_modulo_y_su_profesor(cliente_de, rosa, modulo):
    html = cliente_de(rosa).get(reverse("mensajes:index")).content.decode()
    assert "Escribe a tus profesores" in html and "Prof. María Torres" in html
    assert "Sin mensajes todavía" in html and "Nuevo mensaje" in html
    assert 'class="btn btn-borde" href="' + reverse("mensajes:modulo", args=[modulo.pk]) + '"' not in html  # aún no hay mensajes


def test_docente_ve_cuantos_alumnos_tiene(cliente_de, docente, rosa, luis, modulo):
    html = cliente_de(docente).get(reverse("mensajes:index")).content.decode()
    assert "Conversa con tus alumnos" in html and "2 alumnos" in html


def test_alumno_sin_modulos(cliente_de, forastero):
    html = cliente_de(forastero).get(reverse("mensajes:index")).content.decode()
    assert "Todavía no estás en ningún módulo" in html and "Entrar a un módulo" in html


def test_docente_sin_modulos(cliente_de, docente):
    html = cliente_de(docente).get(reverse("mensajes:index")).content.decode()
    assert "Todavía no tienes módulos" in html and "Crear un módulo" in html


def test_tarjeta_con_mensajes_nuevos(cliente_de, docente, rosa, modulo):
    cv = Conversacion.obtener_o_crear(modulo, docente, rosa)
    cv.enviar(rosa, "Profe, ¿qué traigo?")
    cv.enviar(rosa, "Gracias")
    html = cliente_de(docente).get(reverse("mensajes:index")).content.decode()
    assert "2 mensajes nuevos" in html and "Ver mensajes" in html and "Último mensaje:" in html


# ===================================================================== Nivel 3: escribir uno nuevo


def test_alumno_solo_puede_escribirle_a_su_profesor(cliente_de, rosa, modulo, docente):
    html = cliente_de(rosa).get(reverse("mensajes:nuevo") + f"?curso={modulo.pk}").content.decode()
    assert "Prof. María Torres (Docente)" in html and "Todos los alumnos" not in html
    assert f'<option value="{docente.pk}" selected>' in html


def test_docente_elige_alumno_o_todos(cliente_de, docente, rosa, luis, modulo):
    html = cliente_de(docente).get(reverse("mensajes:nuevo") + f"?curso={modulo.pk}&para={luis.pk}").content.decode()
    assert "Elige a un alumno…" in html and "Todos los alumnos (2)" in html
    assert "Paz, Luis (Alumno)" in html and "Quispe Mamani, Rosa (Alumno)" in html
    assert f'<option value="{luis.pk}" selected>' in html


def test_nuevo_sin_curso_usa_el_unico_modulo(cliente_de, rosa, modulo):
    html = cliente_de(rosa).get(reverse("mensajes:nuevo")).content.decode()
    assert "Peluquería – M1" in html and "Enviar" in html


def test_nuevo_sin_curso_y_con_varios_modulos_vuelve_a_la_lista(cliente_de, docente, rosa, modulo):
    Modulo.crear(
        nombre="Peluquería – M2", especialidad="Peluquería y Barbería", periodo="2026-II", turno="tarde", docente=docente
    )
    r = cliente_de(docente).get(reverse("mensajes:nuevo"))
    assert r.status_code == 302 and r["Location"] == reverse("mensajes:index")


def test_modulo_sin_alumnos_en_el_formulario(cliente_de, docente, modulo):
    html = cliente_de(docente).get(reverse("mensajes:nuevo") + f"?curso={modulo.pk}").content.decode()
    assert "todavía no tiene alumnos a quienes escribir" in html


def test_formulario_de_un_modulo_ajeno(cliente_de, otro_docente, forastero, modulo, rosa):
    assert cliente_de(otro_docente).get(reverse("mensajes:nuevo") + f"?curso={modulo.pk}").status_code == 403
    assert cliente_de(forastero).get(reverse("mensajes:nuevo") + f"?curso={modulo.pk}").status_code == 403
    assert cliente_de(rosa).get(reverse("mensajes:nuevo") + "?curso=999999").status_code == 404


# ===================================================================== Enviar


def test_alumno_envia_y_el_docente_lo_recibe(cliente_de, docente, rosa, modulo):
    c = cliente_de(rosa)
    r = escribir(c, modulo, docente.pk, "Profe, ¿qué traigo mañana?")
    cv = conversacion(modulo, docente, rosa)
    assert r.status_code == 302 and r["Location"] == reverse("mensajes:ver", args=[cv.pk]) + "#ultimo"
    assert "Mensaje enviado." in c.get(r["Location"]).content.decode()
    assert Mensaje.objects.get().texto == "Profe, ¿qué traigo mañana?"
    assert menu.contar("mensajes", docente) == 1 and menu.contar("mensajes", rosa) == 0


def test_docente_envia_a_un_alumno(cliente_de, docente, rosa, luis, modulo):
    escribir(cliente_de(docente), modulo, luis.pk, "Luis, entrega tu trabajo")
    assert Conversacion.objects.count() == 1
    assert menu.contar("mensajes", luis) == 1 and menu.contar("mensajes", rosa) == 0


def test_escribir_dos_veces_usa_la_misma_conversacion(cliente_de, docente, rosa, modulo):
    c = cliente_de(rosa)
    escribir(c, modulo, docente.pk, "Uno")
    escribir(c, modulo, docente.pk, "Dos")
    assert Conversacion.objects.count() == 1 and Mensaje.objects.count() == 2


def test_hay_que_elegir_a_quien_escribir(cliente_de, rosa, modulo):
    c = cliente_de(rosa)
    r = escribir(c, modulo, "", "Hola")
    assert r["Location"] == reverse("mensajes:nuevo") + f"?curso={modulo.pk}"
    html = c.get(r["Location"]).content.decode()
    assert "Elige a quién le escribes." in html and "Hola" in html  # conserva lo escrito
    assert Mensaje.objects.count() == 0


def test_mensaje_vacio_no_se_envia(cliente_de, docente, rosa, modulo):
    c = cliente_de(rosa)
    r = escribir(c, modulo, docente.pk, "   ")
    assert "Escribe tu mensaje (o adjunta una foto) antes de enviarlo." in c.get(r["Location"]).content.decode()
    assert Conversacion.objects.count() == 0


def test_el_texto_largo_se_corta_a_3000(cliente_de, docente, rosa, modulo):
    escribir(cliente_de(rosa), modulo, docente.pk, "a" * 3500)
    assert len(Mensaje.objects.get().texto) == 3000


def test_no_se_puede_escribir_a_otro_docente_ni_a_un_compañero(cliente_de, otro_docente, rosa, luis, modulo):
    c = cliente_de(rosa)
    assert escribir(c, modulo, otro_docente.pk).status_code == 403  # no es el docente del módulo
    assert escribir(c, modulo, luis.pk).status_code == 403  # un compañero
    assert Conversacion.objects.count() == 0


def test_el_docente_solo_escribe_a_sus_alumnos(cliente_de, docente, forastero, modulo):
    assert escribir(cliente_de(docente), modulo, forastero.pk).status_code == 403
    assert escribir(cliente_de(docente), modulo, "abc").status_code == 404


def test_un_alumno_no_puede_escribir_a_todos(cliente_de, rosa, luis, modulo):
    assert escribir(cliente_de(rosa), modulo, "todos").status_code == 403
    assert Conversacion.objects.count() == 0


def test_no_se_escribe_en_un_modulo_ajeno(cliente_de, forastero, docente, modulo):
    assert escribir(cliente_de(forastero), modulo, docente.pk).status_code == 403


def test_docente_envia_a_todos_desde_el_formulario_nuevo(cliente_de, docente, rosa, luis, modulo):
    c = cliente_de(docente)
    r = escribir(c, modulo, "todos", "Mañana hay examen")
    assert r["Location"] == reverse("mensajes:modulo", args=[modulo.pk])
    assert "Mensaje enviado a 2 alumnos de Peluquería – M1." in c.get(r["Location"]).content.decode()
    assert Conversacion.objects.count() == 2 and Mensaje.objects.count() == 2
    assert menu.contar("mensajes", rosa) == 1 and menu.contar("mensajes", luis) == 1


def test_todos_en_un_modulo_sin_alumnos(cliente_de, docente, modulo):
    c = cliente_de(docente)
    r = escribir(c, modulo, "todos")
    assert "Este módulo todavía no tiene alumnos." in c.get(r["Location"]).content.decode()


# ===================================================================== Nivel 2: leer y responder


def test_abrir_la_conversacion_marca_como_leido(cliente_de, docente, rosa, modulo):
    cv = Conversacion.obtener_o_crear(modulo, docente, rosa)
    cv.enviar(rosa, "Profe, tengo una duda")
    assert menu.contar("mensajes", docente) == 1
    html = cliente_de(docente).get(reverse("mensajes:ver", args=[cv.pk])).content.decode()
    assert "Profe, tengo una duda" in html and "Quispe Mamani" in html and 'id="ultimo"' in html
    assert menu.contar("mensajes", docente) == 0
    # la alumna ve que su mensaje ya fue leído
    assert "Leído" in cliente_de(rosa).get(reverse("mensajes:ver", args=[cv.pk])).content.decode()


def test_mensaje_propio_sin_leer_dice_enviado(cliente_de, docente, rosa, modulo):
    cv = Conversacion.obtener_o_crear(modulo, docente, rosa)
    cv.enviar(rosa, "Hola")
    html = cliente_de(rosa).get(reverse("mensajes:ver", args=[cv.pk])).content.decode()
    assert "Enviado" in html and "Leído" not in html
    assert "Escuchar" not in html  # el botón de voz es solo para lo que escribe la otra persona


def test_responder_en_la_conversacion(cliente_de, docente, rosa, modulo):
    cv = Conversacion.obtener_o_crear(modulo, docente, rosa)
    cv.enviar(rosa, "Hola")
    c = cliente_de(docente)
    r = c.post(reverse("mensajes:ver", args=[cv.pk]), {"texto": "Trae tus tijeras"})
    assert r["Location"] == reverse("mensajes:ver", args=[cv.pk]) + "#ultimo"
    html = c.get(r["Location"]).content.decode()
    assert "Trae tus tijeras" in html and "Escuchar" in html  # «Hola» de la alumna sí se puede escuchar
    assert menu.contar("mensajes", rosa) == 1


def test_responder_vacio(cliente_de, docente, rosa, modulo):
    cv = Conversacion.obtener_o_crear(modulo, docente, rosa)
    c = cliente_de(rosa)
    r = c.post(reverse("mensajes:ver", args=[cv.pk]), {"texto": ""})
    assert "Escribe tu mensaje (o adjunta una foto) antes de enviarlo." in c.get(r["Location"]).content.decode()
    assert Mensaje.objects.count() == 0


def test_lista_del_modulo_con_buscador_y_contador(cliente_de, docente, rosa, luis, modulo):
    Conversacion.obtener_o_crear(modulo, docente, rosa).enviar(rosa, "Hola profe")
    Conversacion.obtener_o_crear(modulo, docente, luis).enviar(docente, "Luis, ven")
    html = cliente_de(docente).get(reverse("mensajes:modulo", args=[modulo.pk])).content.decode()
    assert 'data-buscar="rosa quispe mamani"' in html and 'data-buscar="luis paz"' in html
    assert "Elige un mensaje" in html and "(Usted)" in html and 'aria-label="1 sin leer"' in html
    assert "Hola profe" in html


def test_la_lista_pone_primero_la_conversacion_mas_reciente(cliente_de, docente, rosa, luis, modulo):
    Conversacion.obtener_o_crear(modulo, docente, rosa).enviar(rosa, "Primero")
    Conversacion.obtener_o_crear(modulo, docente, luis).enviar(luis, "Después")
    html = cliente_de(docente).get(reverse("mensajes:modulo", args=[modulo.pk])).content.decode()
    assert html.index("luis paz") < html.index("rosa quispe mamani")


def test_el_alumno_ve_la_conversacion_con_prof(cliente_de, docente, rosa, modulo):
    Conversacion.obtener_o_crear(modulo, docente, rosa).enviar(docente, "Bienvenida")
    html = cliente_de(rosa).get(reverse("mensajes:modulo", args=[modulo.pk])).content.decode()
    assert "Prof. María Torres" in html and "Docente" in html and "Buscar en este módulo" in html


def test_conversacion_de_otros_no_se_puede_ver(cliente_de, docente, rosa, luis, otro_docente, modulo):
    cv = Conversacion.obtener_o_crear(modulo, docente, rosa)
    cv.enviar(rosa, "Es privado")
    assert cliente_de(luis).get(reverse("mensajes:ver", args=[cv.pk])).status_code == 403
    assert cliente_de(otro_docente).get(reverse("mensajes:ver", args=[cv.pk])).status_code == 403
    assert cliente_de(luis).post(reverse("mensajes:ver", args=[cv.pk]), {"texto": "intruso"}).status_code == 403
    assert cliente_de(rosa).get(reverse("mensajes:ver", args=[99999])).status_code == 404
    assert Mensaje.objects.count() == 1


def test_el_modulo_ajeno_no_muestra_mensajes(cliente_de, docente, rosa, otro_docente, forastero, modulo):
    Conversacion.obtener_o_crear(modulo, docente, rosa).enviar(rosa, "Es privado")
    assert cliente_de(otro_docente).get(reverse("mensajes:modulo", args=[modulo.pk])).status_code == 403
    assert cliente_de(forastero).get(reverse("mensajes:modulo", args=[modulo.pk])).status_code == 403


def test_la_pestana_mensajes_del_modulo(cliente_de, rosa, modulo):
    html = cliente_de(rosa).get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    assert reverse("mensajes:modulo", args=[modulo.pk]) in html


# ===================================================================== Abrir la conversación con una persona


def test_con_una_persona_sin_conversacion_lleva_al_formulario(cliente_de, docente, rosa, modulo):
    r = cliente_de(rosa).get(reverse("mensajes:con", args=[modulo.pk, docente.pk]))
    assert r["Location"] == reverse("mensajes:nuevo") + f"?curso={modulo.pk}&para={docente.pk}"


def test_con_una_persona_con_conversacion_la_abre(cliente_de, docente, rosa, modulo):
    cv = Conversacion.obtener_o_crear(modulo, docente, rosa)
    r = cliente_de(docente).get(reverse("mensajes:con", args=[modulo.pk, rosa.pk]))
    assert r["Location"] == reverse("mensajes:ver", args=[cv.pk]) + "#ultimo"


def test_empezar_conversacion_con_post(cliente_de, docente, rosa, modulo):
    c = cliente_de(rosa)
    r = c.post(reverse("mensajes:con", args=[modulo.pk, docente.pk]), {"texto": "Buenas tardes"})
    cv = conversacion(modulo, docente, rosa)
    assert r["Location"] == reverse("mensajes:ver", args=[cv.pk]) + "#ultimo"
    r2 = c.post(reverse("mensajes:con", args=[modulo.pk, docente.pk]), {"texto": ""})
    assert r2["Location"] == reverse("mensajes:nuevo") + f"?curso={modulo.pk}&para={docente.pk}"


def test_con_personas_que_no_corresponden(cliente_de, docente, rosa, luis, otro_docente, modulo):
    assert cliente_de(rosa).get(reverse("mensajes:con", args=[modulo.pk, luis.pk])).status_code == 403
    assert cliente_de(rosa).get(reverse("mensajes:con", args=[modulo.pk, otro_docente.pk])).status_code == 403
    assert cliente_de(otro_docente).get(reverse("mensajes:con", args=[modulo.pk, rosa.pk])).status_code == 403
    assert cliente_de(rosa).get(reverse("mensajes:con", args=[modulo.pk, 99999])).status_code == 404
    assert cliente_de(rosa).get(reverse("mensajes:con", args=[99999, docente.pk])).status_code == 404


def test_el_boton_mensaje_de_la_lista_de_alumnos(cliente_de, docente, rosa, modulo):
    html = cliente_de(docente).get(reverse("academico:alumnos", args=[modulo.pk])).content.decode()
    assert reverse("mensajes:con", args=[modulo.pk, rosa.pk]) in html


# ===================================================================== Mensaje a todos


def test_pantalla_mensaje_a_todos(cliente_de, docente, rosa, luis, modulo):
    html = cliente_de(docente).get(reverse("mensajes:todos", args=[modulo.pk])).content.decode()
    assert "Le llega a 2 alumnos, a cada uno en privado" in html and "Luis Paz" in html and "Enviar a todos" in html


def test_pantalla_mensaje_a_todos_sin_alumnos(cliente_de, docente, modulo):
    html = cliente_de(docente).get(reverse("mensajes:todos", args=[modulo.pk])).content.decode()
    assert "Este módulo todavía no tiene alumnos" in html and "Enviar a todos" not in html


def test_enviar_a_todos(cliente_de, docente, rosa, luis, modulo):
    c = cliente_de(docente)
    r = c.post(reverse("mensajes:todos", args=[modulo.pk]), {"texto": "Traigan sus materiales"})
    assert r["Location"] == reverse("mensajes:modulo", args=[modulo.pk])
    assert "Mensaje enviado a 2 alumnos de Peluquería – M1." in c.get(r["Location"]).content.decode()
    assert conversacion(modulo, docente, rosa).mensajes.get().texto == "Traigan sus materiales"
    assert conversacion(modulo, docente, luis).mensajes.get().texto == "Traigan sus materiales"
    # cada alumno solo ve lo suyo
    assert "Traigan sus materiales" in cliente_de(rosa).get(reverse("mensajes:modulo", args=[modulo.pk])).content.decode()
    assert Conversacion.objects.filter(alumno=rosa).count() == 1


def test_enviar_a_todos_sin_texto_o_sin_alumnos(cliente_de, docente, modulo, rosa):
    c = cliente_de(docente)
    r = c.post(reverse("mensajes:todos", args=[modulo.pk]), {"texto": " "})
    assert "Escribe tu mensaje" in c.get(r["Location"]).content.decode()
    modulo.quitar_alumno(rosa)
    r = c.post(reverse("mensajes:todos", args=[modulo.pk]), {"texto": "Hola"})
    assert "Este módulo todavía no tiene alumnos." in c.get(r["Location"]).content.decode()
    assert Mensaje.objects.count() == 0


def test_solo_el_docente_del_modulo_envia_a_todos(cliente_de, rosa, otro_docente, admin, modulo):
    for quien in (rosa, otro_docente, admin):
        c = cliente_de(quien)
        assert c.get(reverse("mensajes:todos", args=[modulo.pk])).status_code == 403
        assert c.post(reverse("mensajes:todos", args=[modulo.pk]), {"texto": "Hola"}).status_code == 403
    assert Mensaje.objects.count() == 0


# ===================================================================== Fotos y archivos


def ruta_real(ruta):
    return Path(settings.MEDIA_ROOT) / ruta


def test_enviar_una_foto(cliente_de, docente, rosa, modulo):
    c = cliente_de(rosa)
    r = escribir(c, modulo, docente.pk, "", archivo=muestras.png("corte.png"))
    m = Mensaje.objects.get()
    assert r.status_code == 302 and m.texto == "" and m.archivo_nombre == "corte.png" and ruta_real(m.archivo_ruta).is_file()
    html = c.get(r["Location"]).content.decode()
    assert f'src="{reverse("mensajes:adjunto", args=[m.pk])}"' in html and "Foto enviada" in html


def test_enviar_un_pdf_con_texto(cliente_de, docente, rosa, modulo):
    c = cliente_de(rosa)
    r = escribir(c, modulo, docente.pk, "Mi informe", archivo=muestras.pdf("informe.pdf"))
    html = c.get(r["Location"]).content.decode()
    assert "Mi informe" in html and "informe.pdf" in html and "Foto enviada" not in html


def test_el_archivo_solo_lo_ven_los_dos(cliente_de, docente, rosa, luis, otro_docente, modulo):
    escribir(cliente_de(rosa), modulo, docente.pk, "", archivo=muestras.png())
    m = Mensaje.objects.get()
    url = reverse("mensajes:adjunto", args=[m.pk])
    for quien in (rosa, docente):
        r = cliente_de(quien).get(url)
        assert r.status_code == 200 and r["Content-Type"] == "image/png" and "inline" in r["Content-Disposition"]
    assert cliente_de(luis).get(url).status_code == 403
    assert cliente_de(otro_docente).get(url).status_code == 403
    assert Client().get(url).status_code == 302
    assert cliente_de(rosa).get(reverse("mensajes:adjunto", args=[99999])).status_code == 404


def test_mensaje_sin_archivo_no_tiene_adjunto(cliente_de, docente, rosa, modulo):
    m = Conversacion.obtener_o_crear(modulo, docente, rosa).enviar(rosa, "Solo texto")
    assert cliente_de(rosa).get(reverse("mensajes:adjunto", args=[m.pk])).status_code == 404


def test_archivo_no_permitido(cliente_de, docente, rosa, modulo):
    from django.core.files.uploadedfile import SimpleUploadedFile

    c = cliente_de(rosa)
    malo = SimpleUploadedFile("virus.exe", b"MZ....", content_type="application/octet-stream")
    r = escribir(c, modulo, docente.pk, "mira", archivo=malo)
    assert "Ese tipo de archivo no está permitido" in c.get(r["Location"]).content.decode()
    falso = SimpleUploadedFile("foto.png", b"esto no es una imagen", content_type="image/png")
    r = escribir(c, modulo, docente.pk, "mira", archivo=falso)
    assert "no parece ser lo que dice su nombre" in c.get(r["Location"]).content.decode()
    assert Mensaje.objects.count() == 0 and not list(Path(settings.MEDIA_ROOT).glob("**/*.png"))


def test_foto_en_el_formulario_de_respuesta(cliente_de, docente, rosa, modulo):
    cv = Conversacion.obtener_o_crear(modulo, docente, rosa)
    cliente_de(rosa).post(reverse("mensajes:ver", args=[cv.pk]), {"texto": "", "archivo": muestras.png()})
    assert cv.mensajes.get().archivo_ruta


def test_foto_al_empezar_conversacion(cliente_de, docente, rosa, modulo):
    cliente_de(rosa).post(reverse("mensajes:con", args=[modulo.pk, docente.pk]), {"texto": "", "archivo": muestras.png()})
    assert Mensaje.objects.get().archivo_ruta


def test_eliminar_un_mensaje_borra_su_archivo(cliente_de, docente, rosa, modulo, django_capture_on_commit_callbacks):
    escribir(cliente_de(rosa), modulo, docente.pk, "", archivo=muestras.png())
    m = Mensaje.objects.get()
    archivo = ruta_real(m.archivo_ruta)
    assert archivo.is_file()
    with django_capture_on_commit_callbacks(execute=True):
        m.delete()
    assert not archivo.exists()


def test_el_archivo_de_un_mensaje_a_todos_se_borra_al_quitar_el_ultimo(
    cliente_de, docente, rosa, luis, modulo, django_capture_on_commit_callbacks
):
    escribir(cliente_de(docente), modulo, "todos", "Miren este modelo", archivo=muestras.png("modelo.png"))
    primero, segundo = Mensaje.objects.order_by("id")
    assert primero.archivo_ruta == segundo.archivo_ruta  # un solo archivo para todos
    archivo = ruta_real(primero.archivo_ruta)
    with django_capture_on_commit_callbacks(execute=True):
        primero.delete()
    assert archivo.is_file()  # el otro alumno todavía lo ve
    with django_capture_on_commit_callbacks(execute=True):
        segundo.delete()
    assert not archivo.exists()


def test_eliminar_el_modulo_borra_mensajes_y_archivos(
    cliente_de, docente, rosa, luis, modulo, django_capture_on_commit_callbacks
):
    escribir(cliente_de(rosa), modulo, docente.pk, "con foto", archivo=muestras.png())
    escribir(cliente_de(docente), modulo, luis.pk, "hola Luis")
    archivo = ruta_real(Mensaje.objects.exclude(archivo_ruta="").get().archivo_ruta)
    assert archivo.is_file()
    assert "2 mensajes" in modulo.resumen_al_eliminar()
    with django_capture_on_commit_callbacks(execute=True):
        modulo.eliminar_completo()
    assert not archivo.exists() and Conversacion.objects.count() == 0 and Mensaje.objects.count() == 0


def test_el_resumen_del_modulo_no_cuenta_mensajes_si_no_hay(modulo, rosa):
    assert not any("mensaje" in frase for frase in modulo.resumen_al_eliminar())


def test_conversaciones_de_un_usuario_incluyen_el_ultimo_mensaje(docente, rosa, luis, modulo):
    a = Conversacion.obtener_o_crear(modulo, docente, rosa)
    a.enviar(rosa, "uno")
    a.enviar(docente, "dos")
    Conversacion.obtener_o_crear(modulo, docente, luis)  # sin mensajes
    lista = Conversacion.de_usuario(docente)
    assert [c.otro_usuario for c in lista] == [rosa, luis]  # la que no tiene mensajes va al final
    assert lista[0].ultimo_texto == "dos" and lista[0].ultimo_autor == docente.pk and lista[0].sin_leer == 1
    assert lista[1].ultimo_texto is None and lista[1].sin_leer == 0
