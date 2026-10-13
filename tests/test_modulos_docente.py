"""Lo que hace el docente en su módulo: crearlo, clases, avisos, alumnos y código; y lo que ve el alumno."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.academico.models import Aviso, Clase, Matricula, Modulo, PreguntaClase
from apps.cuentas.models import Rol, Usuario
from apps.nucleo import ajustes
from apps.nucleo.models import Notificacion, Registro

from .conftest import CLAVE

pytestmark = pytest.mark.django_db


@pytest.fixture
def modulo(docente):
    return Modulo.crear(
        nombre="Peluquería – Módulo 1", especialidad="Peluquería y Barbería", modulo="Módulo 1", periodo="2026-II",
        turno="mañana", docente=docente,
    )  # fmt: skip


@pytest.fixture
def otro_docente(db):
    return Usuario.objects.create_user(
        correo="pedro@cetpro.com", nombres="Pedro", apellidos="Ruiz", password=CLAVE, rol=Rol.DOCENTE
    )


def formulario(**cambios):
    return {
        "especialidad": "Peluquería y Barbería",
        "modulo": "Módulo 2",
        "nombre": "",
        "turno": "noche",
        "horario": "",
        **cambios,
    }


# ---------- Mis módulos ----------


def test_docente_sin_modulos_ve_como_empezar(cliente_de, docente):
    html = cliente_de(docente).get(reverse("academico:modulos")).content.decode()
    assert "Todavía no hay módulos" in html and "Crear un módulo" in html and "Cargar plan de estudios" in html


def test_docente_solo_ve_sus_modulos(cliente_de, docente, otro_docente, modulo):
    Modulo.crear(nombre="Ajeno", especialidad="Soldadura Universal", periodo="2026-II", turno="tarde", docente=otro_docente)
    html = cliente_de(docente).get(reverse("academico:modulos")).content.decode()
    assert "Peluquería – Módulo 1" in html and "Ajeno" not in html and f"Código {modulo.codigo_fmt}" in html


def test_admin_ve_todos_los_modulos(cliente_de, admin, modulo):
    html = cliente_de(admin).get(reverse("academico:modulos")).content.decode()
    assert "Todos los módulos" in html and "Peluquería – Módulo 1" in html


# ---------- Crear su módulo ----------


def test_crear_modulo_con_clases_y_fechas(cliente_de, docente):
    c = cliente_de(docente)
    assert "Crear un módulo" in c.get(reverse("academico:nuevo")).content.decode()
    r = c.post(
        reverse("academico:modulos"),
        formulario(
            **{"temas[]": ["Higiene", "Corte básico", "", "Tintes"], "con_fechas": "1", "desde": "2026-10-05", "dias": "7"}
        ),
    )
    m = Modulo.objects.get()
    assert r["Location"] == reverse("academico:modulo", args=[m.pk])
    assert m.docente == docente and m.periodo == ajustes.ajuste("periodo") and m.nombre == "Peluquería y Barbería – Módulo 2"
    clases = list(m.clases.all())
    assert [x.titulo for x in clases] == ["Higiene", "Corte básico", "Tintes"]
    assert [(x.fecha_inicio, x.fecha_fin) for x in clases] == [
        (date(2026, 10, 5), date(2026, 10, 11)),
        (date(2026, 10, 12), date(2026, 10, 18)),
        (date(2026, 10, 19), date(2026, 10, 25)),
    ]
    assert "con 3 clases" in c.get(r["Location"]).content.decode()


def test_crear_modulo_sin_clases_y_con_grupo_de_whatsapp(cliente_de, docente):
    c = cliente_de(docente)
    c.post(reverse("academico:modulos"), formulario(whatsapp_grupo="https://chat.whatsapp.com/abc123"))
    m = Modulo.objects.get()
    assert m.clases.count() == 0 and m.whatsapp_grupo == "https://chat.whatsapp.com/abc123"
    assert "Abrir el grupo de WhatsApp" in c.get(reverse("academico:modulo", args=[m.pk])).content.decode()


@pytest.mark.parametrize(
    ("cambio", "texto"),
    [
        ({"whatsapp_grupo": "http://malo.com"}, "debe empezar con https://chat.whatsapp.com/"),
        ({"turno": ""}, "Elige el curso, el módulo y el turno"),
        ({"especialidad": "Otra"}, "Elige el curso, el módulo y el turno"),
    ],
)
def test_crear_modulo_con_errores(cliente_de, docente, cambio, texto):
    c = cliente_de(docente)
    r = c.post(reverse("academico:modulos"), formulario(**cambio))
    assert r["Location"] == reverse("academico:nuevo") and texto in c.get(r["Location"]).content.decode()
    assert not Modulo.objects.exists()


def test_solo_docentes_crean_modulos(cliente_de, alumno, admin):
    for p in (alumno, admin):
        assert cliente_de(p).post(reverse("academico:modulos"), formulario()).status_code == 403
        assert cliente_de(p).get(reverse("academico:nuevo")).status_code == 403


def test_editar_su_modulo(cliente_de, docente, modulo):
    c = cliente_de(docente)
    assert "Editar módulo" in c.get(reverse("academico:editar", args=[modulo.pk])).content.decode()
    c.post(reverse("academico:editar", args=[modulo.pk]), formulario(nombre="Nuevo nombre", turno="tarde"))
    modulo.refresh_from_db()
    assert (modulo.nombre, modulo.turno, modulo.modulo) == ("Nuevo nombre", "tarde", "Módulo 2")
    assert modulo.docente == docente and modulo.periodo == "2026-II"  # esto no lo cambia el docente


def test_nadie_mas_edita_el_modulo(cliente_de, alumno, otro_docente, modulo):
    for p in (alumno, otro_docente):
        assert cliente_de(p).get(reverse("academico:editar", args=[modulo.pk])).status_code == 403
        assert cliente_de(p).post(reverse("academico:editar", args=[modulo.pk]), formulario()).status_code == 403
    assert cliente_de(otro_docente).get(reverse("academico:modulo", args=[modulo.pk])).status_code == 403
    assert cliente_de(otro_docente).get(reverse("academico:modulo", args=[9999])).status_code == 404


# ---------- Eliminar su módulo ----------


def test_docente_elimina_su_modulo_vacio(cliente_de, docente, modulo):
    c = cliente_de(docente)
    assert "Eliminar módulo" in c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    c.post(reverse("academico:eliminar", args=[modulo.pk]))
    assert not Modulo.objects.exists()


def test_docente_no_elimina_modulo_archivado(cliente_de, docente, modulo):
    modulo.activo = False
    modulo.save()
    c = cliente_de(docente)
    r = c.get(reverse("academico:eliminar", args=[modulo.pk]))
    assert "pídele al administrador que lo elimine" in c.get(r["Location"]).content.decode()
    c.post(reverse("academico:eliminar", args=[modulo.pk]))
    assert Modulo.objects.exists()


def test_docente_no_elimina_si_ya_hay_registros_de_alumnos(cliente_de, docente, modulo, monkeypatch):
    from apps.academico import resumen

    monkeypatch.setattr(resumen, "REGISTROS_DE_ALUMNOS", [lambda m: True])
    c = cliente_de(docente)
    assert (
        'href="' + reverse("academico:eliminar", args=[modulo.pk])
        not in c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    )
    r = c.post(reverse("academico:eliminar", args=[modulo.pk]))
    assert "ya tiene trabajos, tests o asistencia" in c.get(r["Location"]).content.decode()
    assert Modulo.objects.exists()


def test_eliminar_con_alumnos_pide_entiendo(cliente_de, docente, modulo, alumno):
    modulo.matricular(alumno)
    c = cliente_de(docente)
    r = c.post(reverse("academico:eliminar", args=[modulo.pk]))
    assert "Marca la casilla «Entiendo»" in c.get(r["Location"]).content.decode()
    c.post(reverse("academico:eliminar", args=[modulo.pk]), {"entiendo": "1"})
    assert not Modulo.objects.exists()
    assert Registro.objects.filter(detalle__contains="eliminó su módulo").exists()


# ---------- Clases ----------


def test_agregar_varias_clases_a_la_vez(cliente_de, docente, modulo):
    c = cliente_de(docente)
    r = c.post(
        reverse("academico:planificar", args=[modulo.pk]),
        {"temas[]": ["Uno", "Dos"], "con_fechas": "1", "desde": "2026-11-02", "dias": "3"},
    )
    assert r["Location"] == reverse("academico:modulo", args=[modulo.pk]) + "#clases"
    assert [(x.titulo, x.fecha_inicio, x.fecha_fin) for x in modulo.clases.all()] == [
        ("Uno", date(2026, 11, 2), date(2026, 11, 4)),
        ("Dos", date(2026, 11, 5), date(2026, 11, 7)),
    ]
    assert "2 clases creadas. Se abrirán y cerrarán solas" in c.get(r["Location"]).content.decode()


def test_planificar_sin_fechas_deja_las_clases_abiertas(cliente_de, docente, modulo):
    cliente_de(docente).post(reverse("academico:planificar", args=[modulo.pk]), {"temas[]": ["Uno"]})
    c = modulo.clases.get()
    assert c.fecha_inicio is None and c.situacion == "abierta" and c.fechas_texto == "Sin fechas"


@pytest.mark.parametrize(
    ("datos", "texto"),
    [
        ({"temas[]": ["", " "]}, "al menos una clase"),
        ({"temas[]": ["Uno"], "con_fechas": "1", "desde": "2026-11-02", "dias": "0"}, "Revisa cuántos días"),
        ({"temas[]": ["Uno"], "con_fechas": "1", "desde": "mañana", "dias": "7"}, "Revisa cuántos días"),
    ],
)
def test_planificar_con_errores(cliente_de, docente, modulo, datos, texto):
    c = cliente_de(docente)
    r = c.post(reverse("academico:planificar", args=[modulo.pk]), datos)
    assert texto in c.get(r["Location"]).content.decode() and modulo.clases.count() == 0


def test_temas_de_texto_quita_vinetas_y_numeros():
    assert Clase.temas_de_texto("1. Higiene\n- Corte\nClase 3: Tintes\n\n  • Peinados ") == [
        "Higiene",
        "Corte",
        "Tintes",
        "Peinados",
    ]


def test_agregar_una_clase_y_editarla(cliente_de, docente, modulo):
    c = cliente_de(docente)
    r = c.post(
        reverse("academico:clases", args=[modulo.pk]),
        {"tema": "Corte", "descripcion": "Aprenderás la navaja", "fecha_inicio": "2026-10-20"},
    )
    clase = modulo.clases.get()
    assert r["Location"] == reverse("academico:clase", args=[clase.pk]) and clase.descripcion == "Aprenderás la navaja"
    r = c.post(
        reverse("academico:clase", args=[clase.pk]),
        {"tema": "Corte fino", "descripcion": "", "fecha_inicio": "2026-10-21", "fecha_fin": "2026-10-28"},
    )
    clase.refresh_from_db()
    assert (clase.titulo, clase.fecha_inicio, clase.fecha_fin) == ("Corte fino", date(2026, 10, 21), date(2026, 10, 28))
    assert "Clase guardada." in c.get(r["Location"]).content.decode()


@pytest.mark.parametrize(
    ("datos", "texto"),
    [
        ({"tema": ""}, "Escribe el tema de la clase"),
        ({"tema": "X", "fecha_inicio": "2026-10-20", "fecha_fin": "2026-10-10"}, "después de la fecha de inicio"),
        ({"tema": "X", "fecha_inicio": "ayer"}, "Revisa las fechas"),
    ],
)
def test_clase_con_errores(cliente_de, docente, modulo, datos, texto):
    c = cliente_de(docente)
    r = c.post(reverse("academico:clases", args=[modulo.pk]), datos)
    assert texto in c.get(r["Location"]).content.decode() and modulo.clases.count() == 0


def test_mover_y_borrar_clases(cliente_de, docente, modulo):
    a, b, c3 = (Clase.crear(modulo, t) for t in ("A", "B", "C"))
    c = cliente_de(docente)
    c.post(reverse("academico:mover_clase", args=[c3.pk]), {"dir": "antes"})
    assert [x.titulo for x in modulo.clases.all()] == ["A", "C", "B"]
    c.post(reverse("academico:mover_clase", args=[a.pk]), {"dir": "despues"})
    assert [x.titulo for x in modulo.clases.all()] == ["C", "A", "B"]
    c.post(reverse("academico:mover_clase", args=[c3.pk]), {"dir": "antes"})  # ya es la primera: no pasa nada
    assert [x.titulo for x in modulo.clases.all()] == ["C", "A", "B"]
    c.post(reverse("academico:eliminar_clase", args=[b.pk]))
    assert [x.titulo for x in modulo.clases.all()] == ["C", "A"]


def test_no_se_borra_una_clase_con_contenido(cliente_de, docente, modulo, monkeypatch):
    from apps.academico import models

    clase = Clase.crear(modulo, "Con material")
    monkeypatch.setattr(models, "CONTENIDO_DE_CLASE", [lambda c: True])
    c = cliente_de(docente)
    r = c.post(reverse("academico:eliminar_clase", args=[clase.pk]))
    assert "Primero borra los materiales, tareas y formularios" in c.get(r["Location"]).content.decode()
    assert Clase.objects.exists()


def test_abrir_y_cerrar_una_clase_a_mano(cliente_de, docente, modulo):
    clase = Clase.crear(modulo, "Futura", inicio=date.today() + timedelta(days=10))
    assert clase.situacion == "proxima"
    c = cliente_de(docente)
    c.post(reverse("academico:estado_clase", args=[clase.pk]), {"estado": "abierta"})
    clase.refresh_from_db()
    assert clase.situacion == "abierta" and clase.estado == "abierta"
    c.post(reverse("academico:estado_clase", args=[clase.pk]), {"estado": "cerrada"})
    clase.refresh_from_db()
    assert clase.situacion == "cerrada"
    c.post(reverse("academico:estado_clase", args=[clase.pk]), {"estado": "auto"})
    clase.refresh_from_db()
    assert clase.situacion == "proxima"


def test_situacion_segun_las_fechas():
    hoy = date.today()
    assert Clase(fecha_inicio=hoy + timedelta(days=1)).situacion == "proxima"
    assert Clase(fecha_inicio=hoy, fecha_fin=hoy).situacion == "abierta"
    assert Clase(fecha_inicio=hoy - timedelta(days=9), fecha_fin=hoy - timedelta(days=1)).situacion == "cerrada"
    assert Clase().situacion == "abierta"
    assert Clase(fecha_inicio=date(2026, 10, 7), fecha_fin=date(2026, 10, 20)).fechas_texto == "Del 7 al 20 de octubre"
    assert (
        Clase(fecha_inicio=date(2026, 10, 28), fecha_fin=date(2026, 11, 3)).fechas_texto == "Del 28 de octubre al 3 de noviembre"
    )
    assert Clase(fecha_inicio=date(2026, 10, 7)).fechas_texto == "Desde el miércoles 7 de octubre"


def test_nadie_mas_toca_las_clases(cliente_de, otro_docente, alumno, modulo):
    clase = Clase.crear(modulo, "A")
    modulo.matricular(alumno)
    for p in (otro_docente, alumno):
        c = cliente_de(p)
        assert c.post(reverse("academico:clase", args=[clase.pk]), {"tema": "X"}).status_code == 403
        assert c.post(reverse("academico:estado_clase", args=[clase.pk]), {"estado": "cerrada"}).status_code == 403
        assert c.post(reverse("academico:eliminar_clase", args=[clase.pk])).status_code == 403
        assert c.post(reverse("academico:clases", args=[modulo.pk]), {"tema": "X"}).status_code == 403
    assert Clase.objects.get().titulo == "A"


def test_pagina_del_modulo_para_el_docente(cliente_de, docente, modulo):
    Clase.crear(modulo, "Higiene en el taller", descripcion="Aprenderás a limpiar")
    html = cliente_de(docente).get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    assert "Higiene en el taller" in html and "Clase 1" in html and "Agregar clases" in html
    assert modulo.codigo_fmt in html and "Enviar el código por WhatsApp" in html and "Acciones del día" in html
    assert "Escribir un aviso para todo el módulo" in html and "Editar módulo" in html


def test_redireccion_vieja_de_clases(cliente_de, docente, modulo):
    clase = Clase.crear(modulo, "A")
    c = cliente_de(docente)
    assert (
        c.get(reverse("academico:clases", args=[modulo.pk]))["Location"]
        == reverse("academico:modulo", args=[modulo.pk]) + "#clases"
    )
    assert c.get(reverse("academico:clases", args=[modulo.pk]) + f"?clase={clase.pk}")["Location"] == reverse(
        "academico:clase", args=[clase.pk]
    )
    assert (
        c.get(reverse("academico:nueva_actividad", args=[modulo.pk]))["Location"]
        == reverse("academico:clase", args=[clase.pk]) + "#crear"
    )


def test_crear_tarea_sin_clases_lleva_a_agregarlas(cliente_de, docente, modulo):
    c = cliente_de(docente)
    r = c.get(reverse("academico:nueva_actividad", args=[modulo.pk]))
    assert r["Location"].endswith("#agregar-clases") and "Primero crea las clases" in c.get(r["Location"]).content.decode()


# ---------- Avisos ----------


def test_publicar_y_borrar_un_aviso(cliente_de, docente, alumno, modulo):
    modulo.matricular(alumno)
    c = cliente_de(docente)
    c.post(reverse("academico:publicar_aviso", args=[modulo.pk]), {"contenido": "Mañana traer peine y tijera."})
    aviso = Aviso.objects.get()
    assert aviso.titulo == "Mañana traer peine y tijera." and aviso.autor == docente
    assert Notificacion.objects.get(usuario=alumno).mensaje == "Nuevo aviso de tu profesor: Mañana traer peine y tijera."
    assert "Mañana traer peine y tijera." in c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    # El alumno lo ve en su inicio
    html = cliente_de(alumno).get(reverse("nucleo:inicio")).content.decode()
    assert "Avisos de tus profesores" in html and "Mañana traer peine y tijera." in html
    r = c.post(reverse("academico:publicar_aviso", args=[modulo.pk]), {"contenido": " "})
    assert "Escribe el aviso antes de publicarlo" in c.get(r["Location"]).content.decode()
    c.post(reverse("academico:eliminar_aviso", args=[aviso.pk]))
    assert not Aviso.objects.exists()


def test_alumno_no_publica_avisos(cliente_de, alumno, modulo):
    modulo.matricular(alumno)
    assert cliente_de(alumno).post(reverse("academico:publicar_aviso", args=[modulo.pk]), {"contenido": "x"}).status_code == 403


# ---------- Alumnos y código ----------


def test_lista_de_alumnos_del_docente(cliente_de, docente, alumno, modulo):
    modulo.matricular(alumno)
    pendiente = Usuario.objects.crear_alumno("45678912", "Ana", "Rojas", telefono="987654321")
    modulo.matricular(pendiente)
    html = cliente_de(docente).get(reverse("academico:alumnos", args=[modulo.pk])).content.decode()
    assert "2 alumnos" in html and "Quispe Mamani, Rosa" in html and "Aún no creó su contraseña" in html
    assert (
        modulo.codigo_fmt in html and "Cambiar código" in html and "Cerrar inscripciones" in html and "Nueva contraseña" in html
    )


def test_alumno_no_ve_la_lista_de_alumnos(cliente_de, alumno, modulo):
    modulo.matricular(alumno)
    assert cliente_de(alumno).get(reverse("academico:alumnos", args=[modulo.pk])).status_code == 403


def test_cerrar_abrir_y_cambiar_el_codigo(cliente_de, docente, modulo):
    c = cliente_de(docente)
    c.post(reverse("academico:codigo", args=[modulo.pk]), {"accion": "cerrar"})
    modulo.refresh_from_db()
    assert not modulo.inscripcion_abierta
    c.post(reverse("academico:codigo", args=[modulo.pk]), {"accion": "abrir"})
    modulo.refresh_from_db()
    assert modulo.inscripcion_abierta
    r = c.post(reverse("academico:codigo", args=[modulo.pk]), {"accion": "nuevo"})
    modulo.refresh_from_db()
    assert f"Nuevo código: {modulo.codigo_fmt}" in c.get(r["Location"]).content.decode()


def test_docente_da_una_clave_nueva_a_su_alumno(cliente_de, docente, alumno, modulo):
    modulo.matricular(alumno)
    c = cliente_de(docente)
    r = c.post(reverse("academico:clave_alumno", args=[modulo.pk, alumno.pk]))
    html = c.get(r["Location"]).content.decode()
    assert "Contraseña de Rosa Quispe Mamani" in html and "Enviar por WhatsApp" in html and "12345678" in html
    alumno.refresh_from_db()
    assert alumno.debe_cambiar_clave and not alumno.check_password(CLAVE)
    assert "Contraseña de Rosa" not in c.get(r["Location"]).content.decode()  # se muestra una sola vez
    assert Registro.objects.filter(accion="clave", detalle__contains="dio contraseña nueva a su alumno").exists()


def test_clave_nueva_solo_a_alumnos_de_su_modulo(cliente_de, docente, alumno, modulo):
    assert (
        cliente_de(docente).post(reverse("academico:clave_alumno", args=[modulo.pk, alumno.pk])).status_code == 404
    )  # no está en el módulo


def test_docente_quita_un_alumno(cliente_de, docente, alumno, modulo):
    modulo.matricular(alumno)
    cliente_de(docente).post(reverse("academico:quitar_alumno", args=[modulo.pk, alumno.pk]))
    assert not Matricula.objects.exists() and Usuario.objects.filter(pk=alumno.pk).exists()


# ---------- El alumno ----------


def test_alumno_sin_modulos(cliente_de, alumno):
    html = cliente_de(alumno).get(reverse("academico:modulos")).content.decode()
    assert "Todavía no estás en ningún módulo" in html and "Código del módulo" in html


def test_alumno_ve_sus_modulos_y_entra(cliente_de, alumno, modulo, otro_docente):
    modulo.matricular(alumno)
    Modulo.crear(nombre="Ajeno", especialidad="Soldadura Universal", periodo="2026-II", turno="tarde", docente=otro_docente)
    c = cliente_de(alumno)
    html = c.get(reverse("academico:modulos")).content.decode()
    assert (
        "Peluquería – Módulo 1" in html
        and "Ajeno" not in html
        and "¿Te inscribiste en otro módulo?" in html
        and "Abierto" in html
    )
    clase = Clase.crear(modulo, "Primera clase")
    html = c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    assert "Primera clase" in html and "¡Estás al día en este módulo!" in html and "Escribir un aviso" not in html
    assert modulo.codigo not in html  # el código es del docente
    assert c.get(reverse("academico:clase", args=[clase.pk])).status_code == 200


def test_alumno_de_otro_modulo_no_entra(cliente_de, alumno, modulo):
    c = cliente_de(alumno)
    assert c.get(reverse("academico:modulo", args=[modulo.pk])).status_code == 403
    clase = Clase.crear(modulo, "A")
    assert c.get(reverse("academico:clase", args=[clase.pk])).status_code == 403


def test_clase_que_todavia_no_empieza_esta_bloqueada_para_el_alumno(cliente_de, alumno, docente, modulo):
    modulo.matricular(alumno)
    clase = Clase.crear(modulo, "Futura", inicio=date.today() + timedelta(days=5))
    html = cliente_de(alumno).get(reverse("academico:clase", args=[clase.pk])).content.decode()
    assert "Esta clase todavía no empieza" in html
    assert (
        "Esta clase todavía no empieza"
        not in cliente_de(docente).get(reverse("academico:clase", args=[clase.pk])).content.decode()
    )
    assert "Se abre el" in cliente_de(alumno).get(reverse("academico:modulo", args=[modulo.pk])).content.decode()


def test_clase_oculta_no_la_ve_el_alumno(cliente_de, alumno, modulo):
    modulo.matricular(alumno)
    clase = Clase.crear(modulo, "Oculta")
    clase.visible = False
    clase.save()
    c = cliente_de(alumno)
    assert "Esta clase todavía no empieza" in c.get(reverse("academico:clase", args=[clase.pk])).content.decode()
    assert "Oculta" not in c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()


# ---------- Unirse con un código ----------


def test_alumno_se_une_con_un_codigo(cliente_de, alumno, modulo):
    c = cliente_de(alumno)
    r = c.post(reverse("academico:unirse"), {"codigo": modulo.codigo_fmt.lower()})
    assert r["Location"] == reverse("academico:modulo", args=[modulo.pk]) and modulo.es_alumno(alumno)
    assert "¡Listo! Ya estás en Peluquería – Módulo 1." in c.get(r["Location"]).content.decode()
    r = c.post(reverse("academico:unirse"), {"codigo": modulo.codigo})
    assert "Ya estás en este módulo." in c.get(r["Location"]).content.decode()
    assert Matricula.objects.count() == 1


@pytest.mark.parametrize(
    ("preparar", "texto"),
    [
        (lambda m: None, "Ese código no es correcto"),
        (lambda m: setattr(m, "inscripcion_abierta", False) or m.save(), "ya no acepta alumnos nuevos"),
        (lambda m: ajustes.guardar({"registro_abierto": "0"}), "matrículas del periodo están cerradas"),
    ],
)
def test_unirse_con_problemas(cliente_de, alumno, modulo, preparar, texto):
    preparar(modulo)
    c = cliente_de(alumno)
    r = c.post(reverse("academico:unirse"), {"codigo": "ZZZ9999" if texto.startswith("Ese") else modulo.codigo})
    assert r["Location"] == reverse("academico:modulos") and texto in c.get(r["Location"]).content.decode()
    assert not Matricula.objects.exists()


def test_muchos_codigos_equivocados_frenan(cliente_de, alumno, modulo):
    c = cliente_de(alumno)
    for _ in range(15):
        c.post(reverse("academico:unirse"), {"codigo": "ZZZ9999"})
    r = c.post(reverse("academico:unirse"), {"codigo": modulo.codigo})
    assert "Hubo muchos códigos equivocados" in c.get(r["Location"]).content.decode() and not Matricula.objects.exists()


def test_solo_alumnos_se_unen(cliente_de, docente, modulo):
    assert cliente_de(docente).post(reverse("academico:unirse"), {"codigo": modulo.codigo}).status_code == 403


# ---------- Preguntas de la clase ----------


def test_alumno_pregunta_y_el_docente_responde(cliente_de, alumno, docente, modulo):
    modulo.matricular(alumno)
    clase = Clase.crear(modulo, "Corte")
    a, d = cliente_de(alumno), cliente_de(docente)
    r = a.post(reverse("academico:preguntar", args=[clase.pk]), {"texto": "¿La foto puede ser de costado?"})
    pregunta = PreguntaClase.objects.get()
    assert r["Location"].endswith(f"#pregunta-{pregunta.pk}")
    n = Notificacion.objects.get(usuario=docente)
    assert n.mensaje == "Rosa preguntó en «Corte»" and n.enlace.endswith(f"#pregunta-{pregunta.pk}")
    assert "¿La foto puede ser de costado?" in d.get(reverse("academico:clase", args=[clase.pk])).content.decode()
    d.post(reverse("academico:preguntar", args=[clase.pk]), {"texto": "Sí, puede ser.", "padre": str(pregunta.pk)})
    assert Notificacion.objects.get(usuario=alumno).mensaje == "Respondieron tu pregunta en «Corte»"
    html = a.get(reverse("academico:clase", args=[clase.pk])).content.decode()
    assert "Sí, puede ser." in html and "Profesor" in html
    # El alumno borra su pregunta (y se van las respuestas)
    a.post(reverse("academico:borrar_pregunta", args=[pregunta.pk]))
    assert not PreguntaClase.objects.exists()


def test_preguntas_sin_texto_o_sin_permiso(cliente_de, alumno, otro_docente, admin, modulo):
    modulo.matricular(alumno)
    clase = Clase.crear(modulo, "Corte")
    a = cliente_de(alumno)
    r = a.post(reverse("academico:preguntar", args=[clase.pk]), {"texto": " "})
    assert "Escribe tu pregunta o tu respuesta" in a.get(r["Location"]).content.decode()
    assert cliente_de(otro_docente).post(reverse("academico:preguntar", args=[clase.pk]), {"texto": "x"}).status_code == 403
    assert (
        cliente_de(admin).post(reverse("academico:preguntar", args=[clase.pk]), {"texto": "x"}).status_code == 403
    )  # solo lectura
    assert a.post(reverse("academico:preguntar", args=[clase.pk]), {"texto": "x", "padre": "9999"}).status_code == 404


def test_un_alumno_no_borra_la_pregunta_de_otro(cliente_de, alumno, docente, modulo):
    otro = Usuario.objects.create_user(dni="33333333", nombres="Luis", password=CLAVE, rol=Rol.ALUMNO)
    modulo.matricular(alumno)
    modulo.matricular(otro)
    clase = Clase.crear(modulo, "Corte")
    p = PreguntaClase.objects.create(clase=clase, autor=alumno, texto="mía")
    assert cliente_de(otro).post(reverse("academico:borrar_pregunta", args=[p.pk])).status_code == 403
    assert cliente_de(docente).post(reverse("academico:borrar_pregunta", args=[p.pk])).status_code == 302  # el docente sí
    assert PreguntaClase.sin_responder(docente) == 0


def test_campana_de_avisos(cliente_de, alumno):
    Notificacion.crear(alumno, "Hay una tarea nueva", "/cursos/3")
    c = cliente_de(alumno)
    assert 'aria-label="Avisos: 1 nuevos"' in c.get(reverse("cuentas:cuenta")).content.decode()
    html = c.get(reverse("nucleo:avisos")).content.decode()
    assert "Hay una tarea nueva" in html and "Nuevo" in html and 'href="/cursos/3"' in html
    html = c.get(reverse("nucleo:avisos")).content.decode()
    assert "Hay una tarea nueva" in html and ">Nuevo<" not in html  # ya se marcó como leído
    assert 'aria-label="Avisos"' in c.get(reverse("cuentas:cuenta")).content.decode()
