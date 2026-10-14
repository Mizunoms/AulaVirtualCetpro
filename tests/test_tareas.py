"""Tareas: crear, entregar con foto, calificar (con penalidad), bandeja «Por calificar», papelera y copiar el módulo."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academico.models import Clase, Modulo
from apps.cuentas.models import Rol, Usuario
from apps.nucleo import archivos
from apps.nucleo.models import Notificacion, Registro
from apps.tareas.models import Entrega, Material, Tarea

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
def alumno_en_modulo(alumno, modulo):
    modulo.matricular(alumno)
    return alumno


@pytest.fixture
def otro_docente(db):
    return Usuario.objects.create_user(correo="pedro@cetpro.com", nombres="Pedro", password=CLAVE, rol=Rol.DOCENTE)


def manana():
    return (timezone.localdate() + timedelta(days=1)).isoformat()


def crear_tarea(c, modulo, clase, **cambios):
    datos = {
        "titulo": "Foto del corte",
        "instrucciones": "De frente y de perfil",
        "fecha": manana(),
        "hora": "23:59",
        "unidad_id": str(clase.pk),
    }
    return c.post(reverse("tareas:modulo", args=[modulo.pk]), {**datos, **cambios})


def tarea_en(clase, **cambios):
    datos = {"clase": clase, "titulo": "Tarea", "fecha_limite": timezone.now() + timedelta(days=2)}
    return Tarea.objects.create(**{**datos, **cambios})


# ===================================================================== Crear


def test_pantalla_de_nueva_tarea(cliente_de, docente, modulo, clase):
    html = cliente_de(docente).get(reverse("tareas:nueva", args=[modulo.pk]) + f"?clase={clase.pk}").content.decode()
    assert "1. Nombre de la tarea" in html and "Criterios de evaluación" in html and "Clase 1: Corte básico" in html
    assert f'<option value="{clase.pk}" selected>' in html and "Sí, restando puntos" in html and "Clase: Corte básico" in html


def test_crear_una_tarea_y_avisar_a_los_alumnos(cliente_de, docente, alumno_en_modulo, modulo, clase):
    c = cliente_de(docente)
    r = crear_tarea(
        c, modulo, clase, politica_tardia="penalidad", penalidad_puntos="3", tipo_calificacion="rubrica", tipo="grupal"
    )
    t = Tarea.objects.get()
    assert r["Location"] == reverse("tareas:ver", args=[t.pk]) + "?publicada=1"
    assert (t.titulo, t.clase, t.politica_tardia, t.penalidad_puntos, t.tipo_calificacion, t.tipo) == (
        "Foto del corte", clase, "penalidad", Decimal("3"), "rubrica", "grupal",
    )  # fmt: skip
    assert timezone.localtime(t.fecha_limite).strftime("%H:%M") == "23:59"
    assert Notificacion.objects.get(usuario=alumno_en_modulo).mensaje == "Nueva tarea: Foto del corte"
    html = c.get(r["Location"]).content.decode()
    assert "Avisa a tus alumnos por WhatsApp" in html and "Compartir en WhatsApp" in html and "Foto del corte" in html


def test_tarea_en_clase_que_no_empieza_no_avisa(cliente_de, docente, alumno_en_modulo, modulo):
    futura = Clase.crear(modulo, "Futura", inicio=date.today() + timedelta(days=9))
    crear_tarea(cliente_de(docente), modulo, futura)
    assert Tarea.objects.count() == 1 and not Notificacion.objects.exists()


def test_si_no_se_elige_clase_va_a_la_clase_de_ahora_o_crea_la_primera(cliente_de, docente, modulo):
    c = cliente_de(docente)
    crear_tarea(c, modulo, Clase(pk=0), unidad_id="")  # el módulo todavía no tiene clases
    t = Tarea.objects.get()
    assert t.clase.titulo == "Clase 1" and Clase.objects.count() == 1


def test_politica_sin_penalidad_deja_en_cero_los_puntos(cliente_de, docente, modulo, clase):
    crear_tarea(cliente_de(docente), modulo, clase, politica_tardia="acepta", penalidad_puntos="5")
    assert Tarea.objects.get().penalidad_puntos == 0
    crear_tarea(
        cliente_de(docente), modulo, clase, politica_tardia="inventada", tipo_calificacion="rara", tipo="x", penalidad_puntos="99"
    )
    t = Tarea.objects.latest("id")
    assert (t.politica_tardia, t.tipo_calificacion, t.tipo, t.penalidad_puntos) == (
        "penalidad",
        "nota",
        "individual",
        Decimal("20"),
    )


def test_criterios_con_puntos_deben_sumar_20(cliente_de, docente, modulo, clase):
    c = cliente_de(docente)
    r = crear_tarea(c, modulo, clase, **{"criterio_texto[]": ["Foto", "Corte", ""], "criterio_puntos[]": ["10", "8", ""]})
    assert "deben sumar 20. Ahora suman 18" in c.get(r["Location"]).content.decode() and not Tarea.objects.exists()
    r = crear_tarea(c, modulo, clase, **{"criterio_texto[]": ["Foto", "Corte"], "criterio_puntos[]": ["10", "x"]})
    assert "Escribe los puntos de cada criterio" in c.get(r["Location"]).content.decode()
    crear_tarea(
        c,
        modulo,
        clase,
        **{"criterio_texto[]": ["Foto de frente | y perfil", "Corte parejo", ""], "criterio_puntos[]": ["12", "8", ""]},
    )
    t = Tarea.objects.get()
    assert t.criterios == "Foto de frente   y perfil|12\nCorte parejo|8"
    assert [(x["texto"], x["puntos"]) for x in t.lista_criterios] == [("Foto de frente   y perfil", 12), ("Corte parejo", 8)]


def test_criterios_sin_puntos_son_solo_una_lista(cliente_de, docente, modulo, clase):
    crear_tarea(
        cliente_de(docente),
        modulo,
        clase,
        **{"criterio_texto[]": ["Buena luz", "Modelo con capa"], "criterio_puntos[]": ["", ""]},
    )
    assert Tarea.objects.get().criterios == "Buena luz\nModelo con capa"


@pytest.mark.parametrize(
    ("cambio", "texto"),
    [
        ({"titulo": " "}, "Escribe el nombre de la tarea"),
        ({"fecha": ""}, "Elige hasta qué día"),
        ({"fecha": "mañana"}, "Elige hasta qué día"),
        ({"hora": "25:00"}, "Elige hasta qué día"),
    ],
)
def test_crear_tarea_con_errores(cliente_de, docente, modulo, clase, cambio, texto):
    c = cliente_de(docente)
    r = crear_tarea(c, modulo, clase, **cambio)
    assert r["Location"] == reverse("tareas:nueva", args=[modulo.pk])
    html = c.get(r["Location"]).content.decode()
    assert texto in html
    assert not Tarea.objects.exists()


def test_tarea_con_archivo_adjunto(cliente_de, docente, alumno_en_modulo, modulo, clase):
    crear_tarea(cliente_de(docente), modulo, clase, archivo=muestras.pdf("instrucciones.pdf"))
    t = Tarea.objects.get()
    assert t.archivo_nombre == "instrucciones.pdf" and (archivos._base() / t.archivo_ruta).is_file()
    r = cliente_de(alumno_en_modulo).get(reverse("tareas:archivo", args=[t.pk]))
    assert r.status_code == 200 and b"".join(r.streaming_content).startswith(b"%PDF")


def test_solo_el_docente_del_modulo_crea_tareas(cliente_de, alumno_en_modulo, otro_docente, admin, modulo, clase):
    for p in (alumno_en_modulo, otro_docente, admin):
        c = cliente_de(p)
        assert c.get(reverse("tareas:nueva", args=[modulo.pk])).status_code == 403
        assert crear_tarea(c, modulo, clase).status_code == 403
    assert not Tarea.objects.exists()


# ===================================================================== Ver y listar


def test_lista_de_tareas_del_docente(cliente_de, docente, alumno_en_modulo, modulo, clase):
    t = tarea_en(clase, titulo="Foto del corte")
    Entrega.objects.create(tarea=t, alumno=alumno_en_modulo)
    c = cliente_de(docente)
    html = c.get(reverse("tareas:modulo", args=[modulo.pk])).content.decode()
    assert "Foto del corte" in html and "1 de 1 entregó" in html and "1 por calificar" in html and "Crear tarea" in html
    assert "Todavía no creaste formularios" in html


def test_lista_de_tareas_del_alumno_con_su_estado(cliente_de, alumno_en_modulo, modulo, clase):
    por_entregar = tarea_en(clase, titulo="Por entregar")
    entregada = tarea_en(clase, titulo="Entregada")
    calificada = tarea_en(clase, titulo="Calificada")
    vencida = tarea_en(clase, titulo="Vencida", fecha_limite=timezone.now() - timedelta(days=1))
    Entrega.objects.create(tarea=entregada, alumno=alumno_en_modulo)
    Entrega.objects.create(tarea=calificada, alumno=alumno_en_modulo, nota=Decimal("16"), calificado=timezone.now())
    html = cliente_de(alumno_en_modulo).get(reverse("tareas:modulo", args=[modulo.pk])).content.decode()
    for esperado in ("Por entregar", "Entregada", "Nota 16", "No entregada"):
        assert esperado in html
    assert por_entregar and vencida


def test_el_alumno_no_ve_tareas_de_clases_que_no_empiezan(cliente_de, alumno_en_modulo, modulo):
    futura = Clase.crear(modulo, "Futura", inicio=date.today() + timedelta(days=9))
    t = tarea_en(futura, titulo="Secreta")
    c = cliente_de(alumno_en_modulo)
    assert "Secreta" not in c.get(reverse("tareas:modulo", args=[modulo.pk])).content.decode()
    assert c.get(reverse("tareas:ver", args=[t.pk])).status_code == 404


def test_ficha_de_la_tarea_para_el_alumno(cliente_de, alumno_en_modulo, modulo, clase):
    t = tarea_en(
        clase, titulo="Foto del corte", instrucciones="De frente y de perfil", criterios="Foto nítida|12\nCorte parejo|8", politica_tardia="penalidad",
        penalidad_puntos=Decimal("2"),
    )  # fmt: skip
    html = cliente_de(alumno_en_modulo).get(reverse("tareas:ver", args=[t.pk]) + "?desde=inicio").content.decode()
    assert "Lo que pide tu profesor" in html and "De frente y de perfil" in html and "Foto nítida" in html and "12 pts" in html
    assert (
        "apruebas con 11" in html and "se restan 2 puntos" in html and "Tomar foto" in html and "Confirmar y enviar tarea" in html
    )
    assert 'href="/"' in html  # «Volver» al inicio


def test_ficha_de_la_tarea_para_el_docente_con_la_lista_de_alumnos(cliente_de, docente, alumno_en_modulo, modulo, clase):
    ana = Usuario.objects.crear_alumno("45678912", "Ana", "Rojas", telefono="987654321")
    modulo.matricular(ana)
    t = tarea_en(clase, titulo="Foto del corte")
    Entrega.objects.create(tarea=t, alumno=alumno_en_modulo, tardia=True)
    html = cliente_de(docente).get(reverse("tareas:ver", args=[t.pk])).content.decode()
    assert "Quispe Mamani, Rosa" in html and "Tarde · calificar" in html and "No entregó" in html and "Recordar" in html
    assert (
        "https://wa.me/51987654321?text=Hola%20Ana" in html
        and "Recordar a todos por WhatsApp" in html
        and "Borrar esta tarea" in html
    )


def test_nadie_ajeno_ve_la_tarea(cliente_de, alumno, otro_docente, clase):
    t = tarea_en(clase)
    for p in (alumno, otro_docente):
        assert cliente_de(p).get(reverse("tareas:ver", args=[t.pk])).status_code == 403
    assert cliente_de(alumno).get(reverse("tareas:ver", args=[9999])).status_code == 404


def test_administracion_ve_la_tarea_en_solo_lectura(cliente_de, admin, clase):
    t = tarea_en(clase)
    html = cliente_de(admin).get(reverse("tareas:ver", args=[t.pk])).content.decode()
    assert "Borrar esta tarea" not in html


# ===================================================================== Entregar


def entregar(c, t, **datos):
    return c.post(reverse("tareas:entregar", args=[t.pk]), datos)


def test_alumno_entrega_con_foto(cliente_de, alumno_en_modulo, clase):
    t = tarea_en(clase)
    c = cliente_de(alumno_en_modulo)
    r = entregar(c, t, foto=muestras.png("corte.png"), comentario="Me costó el lado izquierdo")
    assert r["Location"] == reverse("tareas:ver", args=[t.pk])
    e = Entrega.objects.get()
    assert (e.alumno, e.archivo_nombre, e.tardia, e.comentario_alumno) == (
        alumno_en_modulo,
        "corte.png",
        False,
        "Me costó el lado izquierdo",
    )
    assert e.es_imagen and (archivos._base() / e.archivo_ruta).is_file()
    html = c.get(r["Location"]).content.decode()
    assert "¡Tarea entregada!" in html and "Ya entregaste esta tarea" in html and "Tu foto entregada" in html
    r = c.get(reverse("tareas:entrega_archivo", args=[e.pk]))
    assert (
        r.status_code == 200
        and b"".join(r.streaming_content).startswith(b"\x89PNG")
        and r["Content-Disposition"].startswith("inline")
    )


def test_entregar_un_archivo_o_un_enlace(cliente_de, alumno_en_modulo, clase):
    c = cliente_de(alumno_en_modulo)
    t1, t2 = tarea_en(clase, titulo="Uno"), tarea_en(clase, titulo="Dos")
    entregar(c, t1, archivo=muestras.pdf("informe.pdf"))
    entregar(c, t2, enlace="https://drive.google.com/file/d/abc")
    assert Entrega.objects.get(tarea=t1).archivo_nombre == "informe.pdf"
    assert Entrega.objects.get(tarea=t2).enlace == "https://drive.google.com/file/d/abc"
    assert "drive.google.com" in c.get(reverse("tareas:ver", args=[t2.pk])).content.decode()


@pytest.mark.parametrize(
    ("datos", "texto"),
    [
        ({}, "Toma una foto o elige un archivo"),
        ({"enlace": "no vale"}, "El enlace no es válido"),
    ],
)
def test_entrega_con_problemas(cliente_de, alumno_en_modulo, clase, datos, texto):
    t = tarea_en(clase)
    c = cliente_de(alumno_en_modulo)
    r = entregar(c, t, **datos)
    assert texto in c.get(r["Location"]).content.decode() and not Entrega.objects.exists()


def test_entregar_un_archivo_raro_no_se_guarda(cliente_de, alumno_en_modulo, clase):
    from django.core.files.uploadedfile import SimpleUploadedFile

    t = tarea_en(clase)
    c = cliente_de(alumno_en_modulo)
    r = entregar(c, t, archivo=SimpleUploadedFile("virus.exe", b"MZ"))
    assert "no está permitido" in c.get(r["Location"]).content.decode() and not Entrega.objects.exists()


def test_entrega_tarde_segun_la_politica(cliente_de, alumno_en_modulo, clase):
    c = cliente_de(alumno_en_modulo)
    vencida = {"fecha_limite": timezone.now() - timedelta(hours=2)}
    no = tarea_en(clase, titulo="No acepta", **vencida)
    si = tarea_en(clase, titulo="Acepta", politica_tardia="acepta", **vencida)
    r = entregar(c, no, foto=muestras.png())
    assert "no acepta entregas tarde" in c.get(r["Location"]).content.decode() and not Entrega.objects.filter(tarea=no).exists()
    assert "ya no acepta entregas" in c.get(reverse("tareas:ver", args=[no.pk])).content.decode()
    entregar(c, si, foto=muestras.png())
    assert Entrega.objects.get(tarea=si).tardia is True


def test_clase_cerrada_no_recibe_entregas(cliente_de, alumno_en_modulo, clase):
    clase.estado = "cerrada"
    clase.save()
    t = tarea_en(clase)
    entregar(cliente_de(alumno_en_modulo), t, foto=muestras.png())
    assert not Entrega.objects.exists()


def test_reenviar_reemplaza_la_foto_y_borra_la_anterior(cliente_de, alumno_en_modulo, clase):
    t = tarea_en(clase)
    c = cliente_de(alumno_en_modulo)
    entregar(c, t, foto=muestras.png("uno.png"))
    primera = Entrega.objects.get().archivo_ruta
    entregar(c, t, foto=muestras.png("dos.png"))
    e = Entrega.objects.get()
    assert e.archivo_nombre == "dos.png" and e.archivo_ruta != primera
    assert not (archivos._base() / primera).exists() and (archivos._base() / e.archivo_ruta).is_file()


def test_una_tarea_calificada_no_se_cambia(cliente_de, alumno_en_modulo, clase):
    t = tarea_en(clase)
    Entrega.objects.create(tarea=t, alumno=alumno_en_modulo, nota=Decimal("15"), calificado=timezone.now())
    c = cliente_de(alumno_en_modulo)
    r = entregar(c, t, foto=muestras.png())
    assert "ya fue calificada" in c.get(r["Location"]).content.decode()
    assert Entrega.objects.get().archivo_ruta == ""


def test_solo_alumnos_del_modulo_entregan(cliente_de, alumno, docente, clase):
    t = tarea_en(clase)
    assert entregar(cliente_de(alumno), t, foto=muestras.png()).status_code == 403  # no está en el módulo
    assert entregar(cliente_de(docente), t, foto=muestras.png()).status_code == 403
    assert not Entrega.objects.exists()


def test_el_archivo_de_una_entrega_es_privado(cliente_de, alumno_en_modulo, docente, admin, otro_docente, modulo, clase):
    otro = Usuario.objects.create_user(dni="33333333", nombres="Luis", password=CLAVE, rol=Rol.ALUMNO)
    modulo.matricular(otro)
    t = tarea_en(clase)
    entregar(cliente_de(alumno_en_modulo), t, foto=muestras.png())
    e = Entrega.objects.get()
    url = reverse("tareas:entrega_archivo", args=[e.pk])
    for persona in (alumno_en_modulo, docente, admin):
        assert cliente_de(persona).get(url).status_code == 200
    for persona in (otro, otro_docente):
        assert cliente_de(persona).get(url).status_code == 403
    assert cliente_de(docente).get(reverse("tareas:entrega_retro", args=[e.pk])).status_code == 404  # todavía no hay devolución


# ===================================================================== Calificar


def entrega_de(alumno, t, **cambios):
    return Entrega.objects.create(tarea=t, alumno=alumno, **cambios)


def calificar(c, e, **datos):
    return c.post(reverse("tareas:calificar", args=[e.pk]), datos)


def test_calificar_con_nota(cliente_de, docente, alumno_en_modulo, clase):
    t = tarea_en(clase, titulo="Foto del corte")
    e = entrega_de(alumno_en_modulo, t, archivo_ruta="", comentario_alumno="Mire profe")
    c = cliente_de(docente)
    html = c.get(reverse("tareas:calificar", args=[e.pk])).content.decode()
    assert "Nota del trabajo (de 0 a 20)" in html and "Mire profe" in html and "Guardar nota" in html
    r = calificar(c, e, nota="16,5", comentario="Muy bien")
    assert r["Location"] == reverse("tareas:por_calificar")
    e.refresh_from_db()
    assert (e.nota, e.comentario_docente, e.calificada) == (Decimal("16.50"), "Muy bien", True) and e.calificado
    assert Notificacion.objects.get(usuario=alumno_en_modulo).mensaje == "Te calificaron «Foto del corte»: 16.5"
    assert Registro.objects.filter(
        accion="notas", detalle__contains="calificó «Foto del corte» de Rosa Quispe Mamani: 16.5"
    ).exists()
    assert "Nota de Rosa guardada: 16.5." in c.get(r["Location"]).content.decode()
    html = cliente_de(alumno_en_modulo).get(reverse("tareas:ver", args=[t.pk])).content.decode()
    assert "Tu nota" in html and "16.5" in html and "Muy bien" in html and "Aprobado" in html


def test_la_penalidad_por_entrega_tarde_se_resta_sola(cliente_de, docente, alumno_en_modulo, clase):
    t = tarea_en(clase, politica_tardia="penalidad", penalidad_puntos=Decimal("2"))
    e = entrega_de(alumno_en_modulo, t, tardia=True)
    c = cliente_de(docente)
    assert "se restan 2 puntos automáticamente" in c.get(reverse("tareas:calificar", args=[e.pk])).content.decode()
    calificar(c, e, nota="15")
    e.refresh_from_db()
    assert e.nota == Decimal("13.00")
    # Al corregir se muestra la nota original (antes de restar)
    assert 'value="15"' in c.get(reverse("tareas:calificar", args=[e.pk])).content.decode()
    calificar(c, e, nota="1")
    e.refresh_from_db()
    assert e.nota == Decimal("0.00")  # nunca baja de cero


def test_calificar_aprobo_o_no_aprobo(cliente_de, docente, alumno_en_modulo, clase):
    t = tarea_en(clase, tipo_calificacion="aprobado")
    e = entrega_de(alumno_en_modulo, t)
    c = cliente_de(docente)
    assert "¿Aprobó?" in c.get(reverse("tareas:calificar", args=[e.pk])).content.decode()
    r = calificar(c, e)
    assert "Elige si aprobó o no aprobó" in c.get(r["Location"]).content.decode() and not Entrega.objects.get().calificada
    calificar(c, e, aprobado="0")
    e.refresh_from_db()
    assert e.aprobado is False and e.nota is None and e.calificada and e.resultado_texto == "No aprobó"
    assert Notificacion.objects.get().mensaje == "Te calificaron «Tarea»"
    calificar(c, e, aprobado="1")
    e.refresh_from_db()
    assert e.aprobado is True


@pytest.mark.parametrize("nota", ["", "abc", "21", "-1", "nan", "inf"])
def test_nota_invalida(cliente_de, docente, alumno_en_modulo, clase, nota):
    e = entrega_de(alumno_en_modulo, tarea_en(clase))
    c = cliente_de(docente)
    r = calificar(c, e, nota=nota)
    assert "La nota debe ser un número de 0 a 20" in c.get(r["Location"]).content.decode()
    e.refresh_from_db()
    assert e.nota is None


def test_devolver_un_archivo_con_la_nota(cliente_de, docente, alumno_en_modulo, clase):
    e = entrega_de(alumno_en_modulo, tarea_en(clase))
    c = cliente_de(docente)
    calificar(c, e, nota="14", retro=muestras.png("correcciones.png"))
    e.refresh_from_db()
    assert e.retro_nombre == "correcciones.png" and (archivos._base() / e.retro_ruta).is_file()
    primera = e.retro_ruta
    calificar(c, e, nota="14", retro=muestras.pdf("guia.pdf"))
    e.refresh_from_db()
    assert e.retro_nombre == "guia.pdf" and not (archivos._base() / primera).exists()
    html = cliente_de(alumno_en_modulo).get(reverse("tareas:ver", args=[e.tarea_id])).content.decode()
    assert "Ver lo que te devolvió tu profesor" in html
    assert cliente_de(alumno_en_modulo).get(reverse("tareas:entrega_retro", args=[e.pk])).status_code == 200


def test_guardar_y_ver_el_siguiente(cliente_de, docente, alumno_en_modulo, modulo, clase):
    luis = Usuario.objects.create_user(dni="33333333", nombres="Luis", apellidos="Paz", password=CLAVE, rol=Rol.ALUMNO)
    modulo.matricular(luis)
    t = tarea_en(clase)
    primera = entrega_de(alumno_en_modulo, t, fecha_entrega=timezone.now() - timedelta(hours=2))
    segunda = entrega_de(luis, t)
    c = cliente_de(docente)
    assert (
        "Guardar nota y ver el siguiente"
        in c.get(reverse("tareas:calificar", args=[primera.pk]) + "?desde=tarea").content.decode()
    )
    r = calificar(c, primera, nota="12", siguiente="1", desde="tarea")
    assert r["Location"] == reverse("tareas:calificar", args=[segunda.pk]) + "?desde=tarea"
    assert "Guardar nota y ver el siguiente" not in c.get(r["Location"]).content.decode()  # ya no hay más
    r = calificar(c, segunda, nota="18", siguiente="1", desde="tarea")
    assert r["Location"] == reverse("tareas:ver", args=[t.pk])


def test_rubrica_con_criterios_suma_la_nota(cliente_de, docente, alumno_en_modulo, clase):
    t = tarea_en(clase, tipo_calificacion="rubrica", criterios="Foto|12\nCorte|8\nSin puntos")
    e = entrega_de(alumno_en_modulo, t)
    html = cliente_de(docente).get(reverse("tareas:calificar", args=[e.pk])).content.decode()
    assert 'data-rubrica="nota"' in html and "Foto" in html and "(máximo 12)" in html and "Sin puntos" not in html


def test_solo_el_docente_del_modulo_califica(cliente_de, alumno_en_modulo, otro_docente, admin, clase):
    e = entrega_de(alumno_en_modulo, tarea_en(clase))
    for p in (alumno_en_modulo, otro_docente, admin):
        c = cliente_de(p)
        assert c.get(reverse("tareas:calificar", args=[e.pk])).status_code == 403
        assert calificar(c, e, nota="20").status_code == 403
    assert Entrega.objects.get().nota is None


def test_entrega_de_tarea_borrada_no_se_califica(cliente_de, docente, alumno_en_modulo, clase):
    t = tarea_en(clase, eliminado=timezone.now())
    e = entrega_de(alumno_en_modulo, t)
    assert cliente_de(docente).get(reverse("tareas:calificar", args=[e.pk])).status_code == 404


# ===================================================================== Bandeja «Por calificar»


def test_bandeja_por_calificar(cliente_de, docente, alumno_en_modulo, modulo, clase):
    t = tarea_en(clase, titulo="Foto del corte", instrucciones="De frente", criterios="Buena luz|20")
    entrega_de(alumno_en_modulo, t, tardia=True, comentario_alumno="Mire profe")
    c = cliente_de(docente)
    html = c.get(reverse("tareas:por_calificar")).content.decode()
    assert "Pendientes (1)" in html and "Rosa Quispe Mamani" in html and "Foto del corte · Peluquería – M1" in html
    assert "Con retraso" in html and "Lo que pediste" in html and "Buena luz" in html and "Abrir y calificar evidencia" in html
    assert "Mire profe" in html and "Los criterios suman 20 puntos" in html
    assert "Calificados recientemente" in html


def test_bandeja_filtros_y_recientes(cliente_de, docente, alumno_en_modulo, modulo, clase, otro_docente):
    t = tarea_en(clase, titulo="Foto")
    e1 = entrega_de(alumno_en_modulo, t, tardia=True)
    c = cliente_de(docente)
    assert "Foto" in c.get(reverse("tareas:por_calificar") + "?estado=tarde").content.decode()
    html = c.get(reverse("tareas:por_calificar") + "?estado=a_tiempo").content.decode()
    assert "No hay trabajos con ese filtro" in html and "Quitar filtros" in html
    html = c.get(reverse("tareas:por_calificar") + f"?modulo={modulo.pk + 99}").content.decode()
    assert "No hay trabajos con ese filtro" in html
    calificar(c, e1, nota="17")
    html = c.get(reverse("tareas:por_calificar")).content.decode()
    assert "¡Todo calificado!" in html and "Pendientes (0)" in html
    html = c.get(reverse("tareas:por_calificar") + "?pestana=recientes").content.decode()
    assert "Nota 17" in html and "Corregir" in html and "Corregir la nota" in html
    assert (
        "Todavía no calificaste nada"
        in cliente_de(otro_docente).get(reverse("tareas:por_calificar") + "?pestana=recientes").content.decode()
    )


def test_bandeja_no_mezcla_trabajos_de_otros_docentes(cliente_de, otro_docente, alumno_en_modulo, clase):
    entrega_de(alumno_en_modulo, tarea_en(clase, titulo="Ajena"))
    assert "Ajena" not in cliente_de(otro_docente).get(reverse("tareas:por_calificar")).content.decode()


def test_bandeja_solo_para_docentes(cliente_de, alumno, admin):
    for p in (alumno, admin):
        assert cliente_de(p).get(reverse("tareas:por_calificar")).status_code == 403


def test_bandeja_elige_el_trabajo_que_se_pide(cliente_de, docente, alumno_en_modulo, modulo, clase):
    luis = Usuario.objects.create_user(dni="33333333", nombres="Luis", apellidos="Paz", password=CLAVE, rol=Rol.ALUMNO)
    modulo.matricular(luis)
    t = tarea_en(clase)
    entrega_de(alumno_en_modulo, t, fecha_entrega=timezone.now() - timedelta(hours=3))
    e2 = entrega_de(luis, t)
    html = cliente_de(docente).get(reverse("tareas:por_calificar") + f"?ver=e{e2.pk}").content.decode()
    assert "De Luis Paz" in html


# ===================================================================== Papelera de tareas


def test_borrar_una_tarea_va_a_la_papelera_con_sus_entregas(cliente_de, docente, alumno_en_modulo, modulo, clase):
    t = tarea_en(clase, titulo="Foto")
    e = entrega_de(alumno_en_modulo, t, nota=Decimal("15"))
    c = cliente_de(docente)
    r = c.post(reverse("tareas:eliminar", args=[t.pk]))
    assert r["Location"] == reverse("academico:clase", args=[clase.pk]) and "papelera" in c.get(r["Location"]).content.decode()
    assert not Tarea.objects.exists() and Tarea.todos.get().eliminado
    assert cliente_de(alumno_en_modulo).get(reverse("tareas:ver", args=[t.pk])).status_code == 404
    assert "Foto" not in cliente_de(alumno_en_modulo).get(reverse("tareas:modulo", args=[modulo.pk])).content.decode()
    assert Entrega.objects.filter(pk=e.pk).exists()
    assert "Foto" in c.get(reverse("academico:papelera", args=[modulo.pk])).content.decode()
    c.post(reverse("academico:papelera", args=[modulo.pk]), {"tipo": "tarea", "item": str(t.pk)})
    assert Tarea.objects.count() == 1 and Entrega.objects.get().nota == Decimal("15")


def test_solo_el_docente_borra_su_tarea(cliente_de, alumno_en_modulo, otro_docente, clase):
    t = tarea_en(clase)
    for p in (alumno_en_modulo, otro_docente):
        assert cliente_de(p).post(reverse("tareas:eliminar", args=[t.pk])).status_code == 403
    assert Tarea.objects.exists()


def test_al_borrar_una_entrega_se_borran_sus_archivos(alumno_en_modulo, clase, django_capture_on_commit_callbacks):
    ruta, _n = archivos.guardar(muestras.png())
    retro, _n = archivos.guardar(muestras.pdf())
    e = entrega_de(alumno_en_modulo, tarea_en(clase), archivo_ruta=ruta, retro_ruta=retro)
    with django_capture_on_commit_callbacks(execute=True):
        e.delete()
    assert not (archivos._base() / ruta).exists() and not (archivos._base() / retro).exists()


# ===================================================================== Con el resto del aula


def test_el_alumno_ve_lo_pendiente_en_su_inicio_y_en_el_modulo(cliente_de, alumno_en_modulo, modulo, clase):
    t = tarea_en(clase, titulo="Foto del corte", fecha_limite=timezone.now() + timedelta(hours=6))
    c = cliente_de(alumno_en_modulo)
    html = c.get(reverse("nucleo:inicio")).content.decode()
    assert "Tienes <strong>1 entrega pendiente</strong>" in html and "Foto del corte" in html and "Subir foto o archivo" in html
    assert f'href="/tareas/{t.pk}?desde=inicio"' in html
    html = c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    assert "Lo que tienes que hacer" in html and "0% de tus tareas hechas" in html and "Tienes 1 tarea por hacer" in html
    assert 'aria-label="1 pendientes"' in html  # el número del menú «Inicio»
    entregar(c, t, foto=muestras.png())
    html = c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    assert "¡Estás al día en este módulo!" in html and "100% de tus tareas hechas" in html and "Hecha" in html


def test_notas_nuevas_en_el_inicio_del_alumno(cliente_de, docente, alumno_en_modulo, clase):
    t = tarea_en(clase, titulo="Foto del corte")
    e = entrega_de(alumno_en_modulo, t)
    calificar(cliente_de(docente), e, nota="17")
    html = cliente_de(alumno_en_modulo).get(reverse("nucleo:inicio")).content.decode()
    assert "Notas nuevas" in html and "Foto del corte" in html and ">17<" in html


def test_el_docente_ve_lo_que_espera_su_nota(cliente_de, docente, alumno_en_modulo, modulo, clase):
    t = tarea_en(clase, titulo="Foto del corte")
    e = entrega_de(alumno_en_modulo, t)
    c = cliente_de(docente)
    html = c.get(reverse("nucleo:inicio")).content.decode()
    assert "Tienes 1 trabajo por calificar." in html and "Calificar ahora" in html and "1 por calificar" in html
    assert f'href="{reverse("tareas:calificar", args=[e.pk])}"' in html  # con un solo trabajo, abre directo
    assert 'aria-label="1 pendientes"' in html  # «Por calificar» en el menú
    html = c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    assert "Calificar entregas (1 pendiente)" in html and "Foto del corte" in html and "1 entregaron" in html
    assert "Próximas fechas" in c.get(reverse("nucleo:inicio")).content.decode()


def test_proximas_fechas_del_docente(cliente_de, docente, alumno_en_modulo, clase):
    t = tarea_en(clase, titulo="Foto del corte")
    entrega_de(alumno_en_modulo, t)
    tarea_en(clase, titulo="Lejana", fecha_limite=timezone.now() + timedelta(days=60))
    html = cliente_de(docente).get(reverse("nucleo:inicio")).content.decode()
    assert "Foto del corte" in html and "1 entregó" in html and "Lejana" not in html


def test_un_modulo_con_entregas_solo_lo_elimina_el_administrador(cliente_de, docente, admin, alumno_en_modulo, modulo, clase):
    entrega_de(alumno_en_modulo, tarea_en(clase))
    c = cliente_de(docente)
    assert "Eliminar módulo" not in c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    r = c.post(reverse("academico:eliminar", args=[modulo.pk]), {"entiendo": "1"})
    assert "ya tiene trabajos, tests o asistencia" in c.get(r["Location"]).content.decode() and Modulo.objects.exists()
    html = cliente_de(admin).get(reverse("academico:admin_eliminar", args=[modulo.pk])).content.decode()
    assert "1 tarea" in html and "1 trabajo entregado" in html
    cliente_de(admin).post(reverse("academico:admin_eliminar", args=[modulo.pk]), {"entiendo": "1"})
    assert not Modulo.objects.exists() and not Entrega.objects.exists() and not Tarea.todos.exists()


def test_una_clase_con_tareas_no_se_borra(cliente_de, docente, clase):
    tarea_en(clase)
    c = cliente_de(docente)
    r = c.post(reverse("academico:eliminar_clase", args=[clase.pk]))
    assert "Primero borra los materiales, tareas y formularios" in c.get(r["Location"]).content.decode()


# ===================================================================== Copiar el módulo


def test_copiar_el_modulo(cliente_de, docente, alumno_en_modulo, modulo, clase, django_capture_on_commit_callbacks):
    from apps.academico.models import UnidadDidactica

    UnidadDidactica.guardar_lista(modulo, [{"nombre": "Corte", "creditos": 2, "horas": 48}])
    clase.fecha_inicio, clase.fecha_fin = date(2026, 10, 5), date(2026, 10, 11)
    clase.save()
    ruta, _n = archivos.guardar(muestras.pdf())
    Material.objects.create(clase=clase, titulo="Guía", tipo="archivo", archivo_ruta=ruta, archivo_nombre="guia.pdf")
    t = tarea_en(
        clase, titulo="Foto", fecha_limite=timezone.make_aware(timezone.datetime(2026, 10, 9, 23, 59)), criterios="Luz|20"
    )
    Entrega.objects.create(tarea=t, alumno=alumno_en_modulo, nota=Decimal("15"))
    c = cliente_de(docente)
    assert "No se copian" in c.get(reverse("academico:copiar", args=[modulo.pk])).content.decode()
    r = c.post(
        reverse("academico:copiar", args=[modulo.pk]),
        {"nombre": "Peluquería – M1 (2027)", "periodo": "2027-I", "desde": "2027-03-01"},
    )
    nuevo = Modulo.objects.exclude(pk=modulo.pk).get()
    assert r["Location"] == reverse("academico:modulo", args=[nuevo.pk])
    assert (nuevo.nombre, nuevo.periodo, nuevo.docente, nuevo.codigo != modulo.codigo) == (
        "Peluquería – M1 (2027)",
        "2027-I",
        docente,
        True,
    )
    assert not nuevo.matriculas.exists()  # sin alumnos
    assert [(u.nombre, u.creditos) for u in nuevo.unidades_didacticas.all()] == [("Corte", 2)]
    nueva_clase = nuevo.clases.get()
    assert (nueva_clase.titulo, nueva_clase.fecha_inicio, nueva_clase.fecha_fin, nueva_clase.estado) == (
        "Corte básico",
        date(2027, 3, 1),
        date(2027, 3, 7),
        "auto",
    )
    nueva_tarea = Tarea.objects.get(clase=nueva_clase)
    assert timezone.localtime(nueva_tarea.fecha_limite).date() == date(2027, 3, 5) and nueva_tarea.criterios == "Luz|20"
    assert not nueva_tarea.entregas.exists()  # sin entregas ni notas
    nuevo_material = Material.objects.get(clase=nueva_clase)
    assert nuevo_material.archivo_ruta != ruta and (archivos._base() / nuevo_material.archivo_ruta).is_file()
    assert (archivos._base() / ruta).is_file()  # el original no se toca


def test_copiar_con_fecha_mala_o_sin_permiso(cliente_de, docente, alumno_en_modulo, otro_docente, modulo):
    c = cliente_de(docente)
    r = c.post(reverse("academico:copiar", args=[modulo.pk]), {"nombre": "x", "periodo": "2027-I", "desde": "pronto"})
    assert "Revisa la fecha de la primera clase" in c.get(r["Location"]).content.decode() and Modulo.objects.count() == 1
    for p in (alumno_en_modulo, otro_docente):
        assert cliente_de(p).post(reverse("academico:copiar", args=[modulo.pk]), {"nombre": "x"}).status_code == 403


# ===================================================================== Que no confunda: ficha del alumno y formulario del docente


def test_la_ficha_antes_de_entregar_muestra_el_plazo_y_el_formulario_de_entrega(cliente_de, alumno_en_modulo, clase):
    t = tarea_en(clase, fecha_limite=timezone.now() + timedelta(days=2))
    html = cliente_de(alumno_en_modulo).get(reverse("tareas:ver", args=[t.pk])).content.decode()
    assert "Vence" in html and "Entrega tu trabajo" in html and "Tomar foto" in html
    assert "Entregada" not in html and "Envíala otra vez" not in html
    assert "<b>Calificación:</b>" in html and "<b>Nota:</b>" not in html  # sin «Nota: Nota de 0 a 20»
    assert "<b>Si entregas tarde:</b>" not in html and "Después de la fecha ya no se acepta." in html  # sin repetir la frase


def test_despues_de_entregar_lo_primero_que_se_ve_es_que_esta_hecho(cliente_de, alumno_en_modulo, clase):
    t = tarea_en(clase, fecha_limite=timezone.now() - timedelta(days=1), politica_tardia="acepta")
    entrega_de(alumno_en_modulo, t, tardia=True)
    html = cliente_de(alumno_en_modulo).get(reverse("tareas:ver", args=[t.pk])).content.decode()
    assert "Entregada · fuera de fecha" in html and "Ya entregaste esta tarea" in html
    assert "Venció" not in html  # ya no sale el aviso rojo de que se pasó la fecha
    # Enviarla otra vez sigue disponible, pero plegado: no parece que falte algo por hacer
    assert "¿Te equivocaste? Envíala otra vez" in html and "<details" in html and "Entrega tu trabajo" not in html
    assert 'name="foto"' in html


def test_una_tarea_ya_calificada_no_ofrece_enviarla_otra_vez(cliente_de, alumno_en_modulo, clase):
    t = tarea_en(clase)
    entrega_de(alumno_en_modulo, t, nota=Decimal("15"), calificado=timezone.now())
    html = cliente_de(alumno_en_modulo).get(reverse("tareas:ver", args=[t.pk])).content.decode()
    assert "Entregada y calificada" in html and "Tu nota" in html and "Envíala otra vez" not in html


def criterios_abiertos(html):
    """¿El bloque «Criterios de evaluación (opcional)» del formulario de nueva tarea viene desplegado?"""
    import re

    m = re.search(
        r'<details class="tarjeta" ?(open)?>\s*<summary[^>]*>\s*<span class="cuerpo"><span class="fw-bold">Criterios', html
    )
    assert m, "no está el bloque plegable de criterios"
    return bool(m.group(1))


def test_los_criterios_son_opcionales_y_vienen_plegados(cliente_de, docente, modulo, clase):
    c = cliente_de(docente)
    html = c.get(reverse("tareas:nueva", args=[modulo.pk]) + f"?clase={clase.pk}").content.decode()
    assert not criterios_abiertos(html)
    assert 'name="criterio_texto[]"' in html and "de 20 puntos" in html  # siguen ahí, solo plegados
    # Si el formulario vuelve con un error, no se pierde lo que ya había escrito en los criterios
    r = crear_tarea(c, modulo, clase, titulo="", **{"criterio_texto[]": ["Foto clara"], "criterio_puntos[]": ["20"]})
    html = c.get(r["Location"]).content.decode()
    assert criterios_abiertos(html) and "Foto clara" in html
