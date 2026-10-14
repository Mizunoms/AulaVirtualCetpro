"""Inicio de cada rol y página del módulo con contenido (materiales y tareas de prueba)."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academico import contenido, reportes
from apps.academico.contenido import ItemClase
from apps.academico.models import Clase, Modulo
from apps.cuentas.models import Rol, Usuario

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


@pytest.fixture
def con_contenido(monkeypatch, modulo):
    """Un material y dos tareas (una por vencer, otra hecha) dentro de la clase de ahora."""
    clase = Clase.crear(modulo, "Armado de una PC")
    ahora = timezone.now()
    # «Vence hoy»: a las 11:59 de la noche de hoy (no «dentro de 5 horas», que de noche ya cae mañana)
    fin_de_hoy = timezone.localtime(ahora).replace(hour=23, minute=59, second=0, microsecond=0)

    def proveedor(m, usuario, acceso):
        if m.pk != modulo.pk:
            return []
        return [
            ItemClase(clase.pk, "material", "Guía de armado", "/materiales/1", etiqueta="PDF", color="ico-rojo", accion="Descargar", detalle="Toca para abrir"),
            ItemClase(
                clase.pk, "tarea", "Foto de la PC armada", "/tareas/7", icono="camara", color="ico-ambar", boton="Subir foto o archivo",
                limite=fin_de_hoy, chip="Por entregar", chip_clase="chip-aviso", cuenta_en_avance=True,
                clase_titulo=clase.titulo, modulo_nombre=m.nombre, modulo_id=m.pk, id=7, detalle="Entregar foto o archivo",
            ),
            ItemClase(
                clase.pk, "examen", "Test de componentes", "/examenes/3", icono="examen", color="ico-azul", boton="Responder",
                limite=ahora + timedelta(days=9), chip="Nota 16", chip_clase="chip-ok", hecha=True, cuenta_en_avance=True,
                resultado="Ya respondiste · Tu nota: 16", clase_titulo=clase.titulo, modulo_nombre=m.nombre, modulo_id=m.pk, id=3,
            ),
        ]  # fmt: skip

    monkeypatch.setattr(contenido, "PROVEEDORES", [proveedor])
    monkeypatch.setattr(
        contenido,
        "PENDIENTES_DE_ALUMNO",
        [lambda a: [it for it in proveedor(modulo, a, "alumno") if it.pendiente]],
    )
    return clase


# ---------- Alumno ----------


def test_inicio_alumno_sin_modulos(cliente_de, alumno):
    html = cliente_de(alumno).get(reverse("nucleo:inicio")).content.decode()
    assert "¡Hola, Rosa!" in html and "Entra a tu módulo con el código de tu profesor." in html and "Código del módulo" in html


def test_inicio_alumno_con_pendientes(cliente_de, alumno, modulo, con_contenido):
    modulo.matricular(alumno)
    html = cliente_de(alumno).get(reverse("nucleo:inicio")).content.decode()
    assert "Tienes <strong>1 entrega pendiente</strong>" in html
    assert "Foto de la PC armada" in html and "Vence hoy" in html and "Subir foto o archivo" in html and "urgente" in html
    assert "Continuar mi clase: Armado de una PC" in html and "50% hecho" in html  # 1 de 2 hechas
    assert "Test de componentes" not in html.split("Por hacer")[1].split("Mis módulos")[0]  # lo hecho no está por hacer
    assert "con-entrega" in html  # el calendario marca el día de entrega
    assert "Mi asistencia" in html and "Sin clases registradas aún" in html and "Horario de tus talleres" in html


def test_inicio_alumno_muestra_ayuda_y_documentos(cliente_de, alumno, modulo):
    from apps.nucleo import ajustes

    modulo.matricular(alumno)
    ajustes.guardar(
        {"whatsapp": "987654321", "reglamento_url": "https://x.pe/reglamento.pdf", "horario_atencion": "Lunes a viernes"}
    )
    html = cliente_de(alumno).get(reverse("nucleo:inicio")).content.decode()
    assert "¿Problemas con el aula?" in html and "https://wa.me/51987654321" in html and "https://x.pe/reglamento.pdf" in html


def test_mis_modulos_del_alumno_con_pendientes(cliente_de, alumno, modulo, con_contenido):
    modulo.matricular(alumno)
    html = cliente_de(alumno).get(reverse("academico:modulos")).content.decode()
    assert "1 pendiente" in html and "Tareas pendientes" in html and "Vence hoy" in html and "Foto de la PC armada" in html
    assert "50% hecho" in html


def test_pagina_del_modulo_para_el_alumno_con_contenido(cliente_de, alumno, modulo, con_contenido):
    modulo.matricular(alumno)
    html = cliente_de(alumno).get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    assert "Lo que tienes que hacer" in html and "1 pendiente" in html and "Foto de la PC armada" in html
    assert "50% de tus tareas hechas" in html and "Guía de armado" in html and "Descargar" in html
    assert "Tienes 1 tarea por hacer" in html and "Por entregar" in html and "Nota 16" in html
    assert "Tu avance" in html and "Escribir a mi profesor" in html


def test_clase_para_el_alumno_con_contenido(cliente_de, alumno, modulo, con_contenido):
    modulo.matricular(alumno)
    html = cliente_de(alumno).get(reverse("academico:clase", args=[con_contenido.pk])).content.decode()
    assert "Tareas de esta clase" in html and "Ya respondiste · Tu nota: 16" in html and "Subir foto o archivo" in html
    assert "Para ver y leer" in html and "Guía de armado" in html and "Preguntas de la clase" in html


# ---------- Docente ----------


def test_inicio_docente_sin_modulos(cliente_de, docente):
    html = cliente_de(docente).get(reverse("nucleo:inicio")).content.decode()
    assert "Hola, profe María" in html and "Todavía no tienes módulos" in html and "Crear un módulo" in html


def test_inicio_docente_con_modulos(cliente_de, docente, alumno, modulo, con_contenido):
    modulo.matricular(alumno)
    html = cliente_de(docente).get(reverse("nucleo:inicio")).content.decode()
    assert "¡Todo calificado! Buen trabajo." in html and "Soporte – Módulo 1" in html and f"Código {modulo.codigo_fmt}" in html
    assert "1 alumno" in html and "Asistencia de hoy" in html and "Registrar asistencia de hoy" in html and "Pendiente" in html


def test_inicio_docente_con_trabajos_por_calificar(cliente_de, docente, modulo, monkeypatch):
    monkeypatch.setattr(contenido, "ESPERANDO_NOTA", [lambda d: [("/entregas/5", modulo.pk), ("/entregas/6", modulo.pk)]])
    html = cliente_de(docente).get(reverse("nucleo:inicio")).content.decode()
    assert "Tienes 2 trabajos por calificar." in html and "Calificar ahora" in html and "2 por calificar" in html


def test_pagina_del_modulo_con_contenido_para_el_docente(cliente_de, docente, modulo, con_contenido, monkeypatch):
    monkeypatch.setattr(contenido, "POR_CALIFICAR", [lambda m: 3])
    html = cliente_de(docente).get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    assert "1 material · 2 tareas" in html and "Guía de armado" in html and "Calificar entregas (3 pendientes)" in html
    assert "Subir material" in html and "Crear tarea" in html


# ---------- Administración y dirección ----------


def test_inicio_admin(cliente_de, admin, alumno, docente, modulo):
    Usuario.objects.crear_alumno("45678912", "Ana", "Rojas")  # sin contraseña aún
    html = cliente_de(admin).get(reverse("nucleo:inicio")).content.decode()
    assert "Panel de administración" in html and "Reportes de la semana" in html and "Configurar el aula" in html
    assert "Docentes" in html and "Módulos activos" in html and "Sin contraseña aún" in html
    assert "Todavía no hay asistencia registrada esta semana" in html and "Todavía no hay trabajos ni tests entregados" in html
    assert "Últimos accesos" in html and "Movimientos recientes" in html


def test_inicio_admin_cuenta_bien(cliente_de, admin, alumno, docente, modulo):
    Usuario.objects.crear_alumno("45678912", "Ana", "Rojas")
    from django.test import RequestFactory

    from apps.academico.views_inicio import contexto_admin

    req = RequestFactory().get("/")
    req.user = admin
    ctx = contexto_admin(req)
    kpis = {k[2]: k[1] for k in ctx["kpis"]}
    assert kpis == {"Docentes": 1, "Alumnos": 2, "Módulos activos": 1, "Sin contraseña aún": 1}


def test_inicio_admin_con_reportes(cliente_de, admin, monkeypatch):
    monkeypatch.setattr(
        reportes, "ASISTENCIA_SEMANA", [lambda: {"pct": 64, "registros": 40, "sesiones": 5, "desde": timezone.localdate()}]
    )
    monkeypatch.setattr(
        reportes,
        "NOTAS_POR_MODULO",
        [
            lambda: [
                {
                    "id": 1,
                    "nombre": "Soporte",
                    "especialidad": "Soporte Técnico",
                    "docente": "María Torres",
                    "calificadas": 8,
                    "pendientes": 2,
                    "pct": 80,
                }
            ]
        ],
    )
    html = cliente_de(admin).get(reverse("nucleo:inicio")).content.decode()
    assert (
        "64<small>%</small>" in html
        and "8" in html
        and "80% de lo entregado ya tiene nota" in html
        and "Calificación al día, por módulo" in html
    )


def test_inicio_direccion_lista_los_modulos(cliente_de, modulo):
    direccion = Usuario.objects.create_user(correo="dir@cetpro.com", nombres="Dora", password=CLAVE, rol=Rol.DIRECCION)
    html = cliente_de(direccion).get(reverse("nucleo:inicio")).content.decode()
    assert "Panel de dirección" in html and "Soporte – Módulo 1" in html and "Configurar el aula" not in html
    assert "Prof. María Torres" in html
    assert cliente_de(direccion).get(reverse("academico:modulo", args=[modulo.pk])).status_code == 200  # solo lectura


def test_direccion_no_entra_a_ajustes(cliente_de, modulo):
    direccion = Usuario.objects.create_user(correo="dir@cetpro.com", nombres="Dora", password=CLAVE, rol=Rol.DIRECCION)
    assert cliente_de(direccion).get(reverse("nucleo:ajustes")).status_code == 403
    assert cliente_de(direccion).get(reverse("academico:admin_modulos")).status_code == 403


def test_nombre_corto_del_modulo(modulo):
    from apps.nucleo.templatetags.aula import nombre_corto_modulo

    assert nombre_corto_modulo(modulo) == "Soporte Técnico 1"
    modulo.especialidad, modulo.modulo = "Peluquería y Barbería", "Módulo 2"
    assert nombre_corto_modulo(modulo) == "Peluquería 2"


def test_calendario_del_mes():
    from apps.academico.views_inicio import _calendario

    hoy = timezone.localdate()
    cal = _calendario({hoy.isoformat(): ["Una tarea"]})
    celdas = [c for semana in cal["semanas"] for c in semana if c]
    assert all(len(s) == 7 for s in cal["semanas"]) and len(celdas) >= 28
    celda_hoy = next(c for c in celdas if c["dia"] == hoy.day)
    assert celda_hoy["clases"] == "hoy con-entrega" and celda_hoy["titulo"] == "Una tarea"
