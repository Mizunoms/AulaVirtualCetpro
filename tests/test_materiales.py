"""Materiales de las clases: subir, abrir con permisos, papelera y recuperar."""

from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.academico import papelera
from apps.academico.models import Clase, Modulo
from apps.cuentas.models import Rol, Usuario
from apps.nucleo import archivos
from apps.tareas.models import Material

from . import muestras
from .conftest import CLAVE

pytestmark = pytest.mark.django_db


@pytest.fixture
def modulo(docente):
    return Modulo.crear(
        nombre="Peluquería – M1", especialidad="Peluquería y Barbería", periodo="2026-II", turno="mañana", docente=docente
    )


@pytest.fixture
def clase(modulo):
    return Clase.crear(modulo, "Corte básico")


@pytest.fixture
def otro_docente(db):
    return Usuario.objects.create_user(correo="pedro@cetpro.com", nombres="Pedro", password=CLAVE, rol=Rol.DOCENTE)


def subir(c, modulo, clase, **datos):
    return c.post(reverse("tareas:material_guardar", args=[modulo.pk]), {"unidad_id": str(clase.pk), **datos})


def test_subir_un_pdf(cliente_de, docente, modulo, clase):
    c = cliente_de(docente)
    r = subir(c, modulo, clase, tipo="archivo", titulo="Guía de corte", archivo=muestras.pdf())
    assert r["Location"] == reverse("academico:clase", args=[clase.pk])
    m = Material.objects.get()
    assert (m.titulo, m.tipo, m.archivo_nombre, m.etiqueta) == ("Guía de corte", "archivo", "guia.pdf", "PDF")
    assert m.archivo_ruta.endswith(".pdf") and (archivos._base() / m.archivo_ruta).is_file()
    assert "Material publicado" in c.get(r["Location"]).content.decode()
    html = c.get(r["Location"]).content.decode()
    assert "Guía de corte" in html and "Toca para abrir" in html


def test_el_titulo_vacio_usa_el_nombre_del_archivo(cliente_de, docente, modulo, clase):
    subir(cliente_de(docente), modulo, clase, tipo="archivo", titulo="", archivo=muestras.png("mi foto.png"))
    assert Material.objects.get().titulo == "mi foto" and Material.objects.get().etiqueta == "Foto"


def test_subir_enlace_y_video(cliente_de, docente, modulo, clase):
    c = cliente_de(docente)
    subir(c, modulo, clase, tipo="enlace", url="https://www.cetpro.edu.pe/normas", titulo="")
    subir(c, modulo, clase, tipo="enlace", url="https://youtu.be/abc123", titulo="Corte en video")
    web, video = Material.objects.order_by("id")
    assert (web.tipo, web.titulo, web.etiqueta) == ("enlace", "Enlace", "Enlace")
    assert (video.tipo, video.titulo, video.etiqueta) == ("video", "Corte en video", "Video")


@pytest.mark.parametrize(
    ("datos", "texto"),
    [
        ({"tipo": "enlace", "url": "no es un enlace"}, "El enlace no es válido"),
        ({"tipo": "enlace", "url": "ftp://x.pe/a"}, "El enlace no es válido"),
        ({"tipo": "enlace", "url": "javascript:alert(1)"}, "El enlace no es válido"),
        ({"tipo": "archivo"}, "Elige el archivo que quieres subir"),
        ({"tipo": "archivo", "archivo": SimpleUploadedFile("virus.exe", b"MZ")}, "no está permitido"),
        ({"tipo": "archivo", "archivo": SimpleUploadedFile("falso.pdf", b"no soy un pdf")}, "no parece ser lo que dice"),
    ],
)
def test_material_con_errores(cliente_de, docente, modulo, clase, datos, texto):
    c = cliente_de(docente)
    r = subir(c, modulo, clase, **datos)
    assert r["Location"] == reverse("academico:clase", args=[clase.pk])
    assert texto in c.get(r["Location"]).content.decode()
    assert not Material.objects.exists()


def test_clase_que_no_es_del_modulo(cliente_de, docente, modulo, otro_docente):
    ajena = Clase.crear(
        Modulo.crear(nombre="O", especialidad="X", periodo="2026-II", turno="tarde", docente=otro_docente), "Otra"
    )
    c = cliente_de(docente)
    r = subir(c, modulo, ajena, tipo="enlace", url="https://x.pe")
    assert "Elige la clase donde va el material" in c.get(r["Location"]).content.decode() and not Material.objects.exists()


def test_solo_el_docente_del_modulo_sube_material(cliente_de, alumno, otro_docente, admin, modulo, clase):
    modulo.matricular(alumno)
    for p in (alumno, otro_docente, admin):
        assert subir(cliente_de(p), modulo, clase, tipo="enlace", url="https://x.pe").status_code == 403
    assert not Material.objects.exists()


def test_abrir_un_archivo_y_un_enlace(cliente_de, docente, alumno, modulo, clase):
    modulo.matricular(alumno)
    c = cliente_de(docente)
    subir(c, modulo, clase, tipo="archivo", titulo="Guía", archivo=muestras.pdf())
    subir(c, modulo, clase, tipo="enlace", url="https://www.cetpro.edu.pe/normas", titulo="Normas")
    guia, normas = Material.objects.order_by("id")
    for persona in (docente, alumno):
        r = cliente_de(persona).get(reverse("tareas:material", args=[guia.pk]))
        assert r.status_code == 200 and b"".join(r.streaming_content).startswith(b"%PDF")
        assert r["Content-Disposition"].startswith("inline")  # un PDF se ve en el navegador
        assert r["X-Content-Type-Options"] == "nosniff"
        r = cliente_de(persona).get(reverse("tareas:material", args=[normas.pk]))
        assert r.status_code == 302 and r["Location"] == "https://www.cetpro.edu.pe/normas"


def test_un_archivo_que_no_es_imagen_ni_pdf_se_descarga(cliente_de, docente, modulo, clase):
    c = cliente_de(docente)
    from apps.tareas.models import TipoMaterial

    ruta, _n = archivos.guardar(SimpleUploadedFile("datos.xlsx", b"PK\x03\x04" + b"\x00" * 30))
    m = Material.objects.create(
        clase=clase, titulo="Datos", tipo=TipoMaterial.ARCHIVO, archivo_ruta=ruta, archivo_nombre="datos.xlsx"
    )
    r = c.get(reverse("tareas:material", args=[m.pk]))
    assert r["Content-Disposition"].startswith("attachment") and "datos.xlsx" in r["Content-Disposition"]


def test_permisos_para_abrir_material(cliente_de, alumno, otro_docente, modulo, clase):
    m = Material.objects.create(clase=clase, titulo="x", tipo="enlace", url="https://x.pe")
    assert cliente_de(alumno).get(reverse("tareas:material", args=[m.pk])).status_code == 403  # no está en el módulo
    assert cliente_de(otro_docente).get(reverse("tareas:material", args=[m.pk])).status_code == 403
    assert cliente_de(alumno).get(reverse("tareas:material", args=[9999])).status_code == 404


def test_alumno_no_abre_material_de_una_clase_que_no_empieza(cliente_de, alumno, modulo):
    modulo.matricular(alumno)
    futura = Clase.crear(modulo, "Futura", inicio=date.today() + timedelta(days=9))
    m = Material.objects.create(clase=futura, titulo="x", tipo="enlace", url="https://x.pe")
    assert cliente_de(alumno).get(reverse("tareas:material", args=[m.pk])).status_code == 404


def test_el_alumno_ve_los_materiales_de_su_clase(cliente_de, docente, alumno, modulo, clase):
    modulo.matricular(alumno)
    subir(cliente_de(docente), modulo, clase, tipo="archivo", titulo="Guía de corte", archivo=muestras.pdf())
    c = cliente_de(alumno)
    html = c.get(reverse("academico:clase", args=[clase.pk])).content.decode()
    assert "Para ver y leer" in html and "Guía de corte" in html and "Borrar Guía de corte" not in html
    html = c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    assert "Guía de corte" in html and "Descargar" in html
    assert "Borrar" not in cliente_de(alumno).get(reverse("academico:clase", args=[clase.pk])).content.decode()


# ---------- Papelera ----------


def test_borrar_un_material_lo_manda_a_la_papelera(cliente_de, docente, modulo, clase):
    c = cliente_de(docente)
    subir(c, modulo, clase, tipo="archivo", titulo="Guía", archivo=muestras.pdf())
    m = Material.objects.get()
    r = c.post(reverse("tareas:material_eliminar", args=[m.pk]))
    assert r["Location"] == reverse("academico:clase", args=[clase.pk]) and "papelera" in c.get(r["Location"]).content.decode()
    assert not Material.objects.exists()
    assert Material.todos.get().eliminado is not None
    assert (archivos._base() / m.archivo_ruta).is_file()  # el archivo se conserva 30 días
    assert (
        "Guía"
        not in c.get(reverse("academico:modulo", args=[modulo.pk]))
        .content.decode()
        .split("Agregar clases")[0]
        .split("Clases")[-1]
    )
    html = c.get(reverse("academico:papelera", args=[modulo.pk])).content.decode()
    assert "Guía" in html and "Material" in html and "Corte básico" in html and "30 días" in html
    r = c.post(reverse("academico:papelera", args=[modulo.pk]), {"tipo": "material", "item": str(m.pk)})
    assert r["Location"] == reverse("academico:clase", args=[clase.pk])
    assert Material.objects.count() == 1


def test_material_de_la_papelera_no_se_abre(cliente_de, docente, modulo, clase):
    m = Material.objects.create(clase=clase, titulo="x", tipo="enlace", url="https://x.pe", eliminado=timezone.now())
    assert cliente_de(docente).get(reverse("tareas:material", args=[m.pk])).status_code == 404


def test_recuperar_algo_que_no_existe(cliente_de, docente, modulo):
    c = cliente_de(docente)
    r = c.post(reverse("academico:papelera", args=[modulo.pk]), {"tipo": "material", "item": "999"})
    assert "No se encontró eso en la papelera" in c.get(r["Location"]).content.decode()
    r = c.post(reverse("academico:papelera", args=[modulo.pk]), {"tipo": "otra", "item": "1"})
    assert r["Location"] == reverse("academico:papelera", args=[modulo.pk])


def test_la_papelera_vacia_lo_viejo_y_borra_sus_archivos(cliente_de, docente, modulo, clase, django_capture_on_commit_callbacks):
    c = cliente_de(docente)
    subir(c, modulo, clase, tipo="archivo", titulo="Viejo", archivo=muestras.pdf())
    subir(c, modulo, clase, tipo="enlace", url="https://x.pe", titulo="Reciente")
    viejo, reciente = Material.objects.order_by("id")
    Material.todos.filter(pk=viejo.pk).update(eliminado=timezone.now() - timedelta(days=31))
    Material.todos.filter(pk=reciente.pk).update(eliminado=timezone.now() - timedelta(days=3))
    ruta = viejo.archivo_ruta
    with django_capture_on_commit_callbacks(execute=True):
        assert papelera.vaciar_viejos() == 1
    assert list(Material.todos.values_list("titulo", flat=True)) == ["Reciente"]
    assert not (archivos._base() / ruta).exists()


def test_la_papelera_es_solo_del_docente(cliente_de, alumno, otro_docente, modulo):
    modulo.matricular(alumno)
    for p in (alumno, otro_docente):
        assert cliente_de(p).get(reverse("academico:papelera", args=[modulo.pk])).status_code == 403


def test_borrar_el_modulo_borra_tambien_los_archivos(
    cliente_de, admin, docente, modulo, clase, django_capture_on_commit_callbacks
):
    subir(cliente_de(docente), modulo, clase, tipo="archivo", titulo="Guía", archivo=muestras.pdf())
    m = Material.objects.get()
    ruta = m.archivo_ruta
    html = cliente_de(admin).get(reverse("academico:admin_eliminar", args=[modulo.pk])).content.decode()
    assert "1 material" in html and "1 clase" in html
    with django_capture_on_commit_callbacks(execute=True):
        cliente_de(admin).post(reverse("academico:admin_eliminar", args=[modulo.pk]), {"entiendo": "1"})
    assert not Material.todos.exists() and not (archivos._base() / ruta).exists()


def test_una_clase_con_material_no_se_borra(cliente_de, docente, modulo, clase):
    Material.objects.create(
        clase=clase, titulo="x", tipo="enlace", url="https://x.pe", eliminado=timezone.now()
    )  # ni en la papelera
    c = cliente_de(docente)
    r = c.post(reverse("academico:eliminar_clase", args=[clase.pk]))
    assert "Primero borra los materiales" in c.get(r["Location"]).content.decode() and Clase.objects.exists()
