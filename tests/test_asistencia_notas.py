"""Asistencia, libro de notas (nota final con pesos), Excel, impresión y registro consolidado."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academico.models import Clase, Evaluacion, Modulo
from apps.cuentas.models import Rol, Usuario
from apps.evaluacion import calificacion
from apps.evaluacion.models import Asistencia, SesionAsistencia, porcentajes
from apps.nucleo.models import Registro
from apps.tareas.models import Entrega, Tarea

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
def alumnos(modulo):
    lista = [
        Usuario.objects.create_user(dni=f"4000000{i}", nombres=n, apellidos=a, password=CLAVE, rol=Rol.ALUMNO)
        for i, (n, a) in enumerate([("Rosa", "Quispe"), ("Luis", "Paz"), ("Ana", "Rojas")])
    ]
    for u in lista:
        modulo.matricular(u)
    return lista


@pytest.fixture
def otro_docente(db):
    return Usuario.objects.create_user(correo="pedro@cetpro.com", nombres="Pedro", password=CLAVE, rol=Rol.DOCENTE)


ASIS = "evaluacion:asistencia"


def tomar(c, modulo, estados, fecha=None, **extra):
    datos = {"fecha": (fecha or timezone.localdate()).isoformat(), **extra}
    datos.update({f"estado[{a.pk}]": e for a, e in estados.items()})
    return c.post(reverse(ASIS, args=[modulo.pk]), datos)


# ===================================================================== Asistencia


def test_pantalla_para_tomar_asistencia(cliente_de, docente, alumnos, modulo):
    html = cliente_de(docente).get(reverse(ASIS, args=[modulo.pk])).content.decode()
    assert "Asistencia de hoy" in html and "Todos empiezan como <b>Vino</b>" in html and "Paz, Luis" in html
    assert html.count('value="presente" checked') == 3 and "Guardar asistencia" in html


def test_guardar_asistencia_con_faltas(cliente_de, docente, alumnos, modulo):
    rosa, luis, ana = alumnos
    c = cliente_de(docente)
    r = tomar(c, modulo, {rosa: "presente", luis: "falta", ana: "tarde"}, tema="Corte básico")
    assert r["Location"] == reverse("academico:modulo", args=[modulo.pk])
    assert "Asistencia guardada. Faltaron 1." in c.get(r["Location"]).content.decode()
    s = SesionAsistencia.objects.get()
    assert (s.fecha, s.tema) == (timezone.localdate(), "Corte básico")
    assert {a.alumno: a.estado for a in Asistencia.objects.all()} == {rosa: "presente", luis: "falta", ana: "tarde"}
    assert Registro.objects.filter(accion="notas", detalle__contains="tomó la asistencia de Peluquería – M1").exists()


def test_vinieron_todos_y_estado_raro_cuenta_como_vino(cliente_de, docente, alumnos, modulo):
    c = cliente_de(docente)
    r = tomar(c, modulo, {a: "volando" for a in alumnos})
    assert "Vinieron todos." in c.get(r["Location"]).content.decode()
    assert set(Asistencia.objects.values_list("estado", flat=True)) == {"presente"}


def test_corregir_la_asistencia_del_dia_no_duplica(cliente_de, docente, alumnos, modulo):
    rosa, luis, _ana = alumnos
    c = cliente_de(docente)
    tomar(c, modulo, {rosa: "falta", luis: "presente"})
    html = c.get(reverse(ASIS, args=[modulo.pk])).content.decode()
    assert "ya está guardada. Puedes cambiarla" in html and 'value="falta" checked' in html
    tomar(c, modulo, {rosa: "justificada", luis: "presente"}, tema="Cambió")
    assert SesionAsistencia.objects.count() == 1 and Asistencia.objects.count() == 3
    assert Asistencia.objects.get(alumno=rosa).estado == "justificada" and SesionAsistencia.objects.get().tema == "Cambió"


def test_dias_anteriores(cliente_de, docente, alumnos, modulo):
    rosa, luis, _ana = alumnos
    c = cliente_de(docente)
    ayer = timezone.localdate() - timedelta(days=1)
    tomar(c, modulo, {rosa: "falta", luis: "presente"}, fecha=ayer, tema="Higiene")
    html = c.get(reverse(ASIS, args=[modulo.pk]) + f"?fecha={ayer.isoformat()}").content.decode()
    assert f"Asistencia del {ayer.strftime('%d/%m')}" in html and 'value="falta" checked' in html
    html = c.get(reverse(ASIS, args=[modulo.pk])).content.decode()
    assert "Clases anteriores" in html and "Higiene · Faltaron 1" in html
    assert c.get(reverse(ASIS, args=[modulo.pk]) + "?fecha=cualquier-cosa").status_code == 200  # fecha mala = hoy


@pytest.mark.parametrize("fecha", ["", "mañana", "2099-01-01"])
def test_fecha_no_valida(cliente_de, docente, alumnos, modulo, fecha):
    c = cliente_de(docente)
    r = c.post(reverse(ASIS, args=[modulo.pk]), {"fecha": fecha})
    assert "Elige una fecha válida" in c.get(r["Location"]).content.decode() and not SesionAsistencia.objects.exists()


def test_porcentaje_tarde_y_justificada_cuentan_como_asistencia(cliente_de, docente, alumnos, modulo):
    rosa, luis, ana = alumnos
    c = cliente_de(docente)
    for dias, estados in enumerate(
        [
            {rosa: "presente", luis: "falta", ana: "tarde"},
            {rosa: "falta", luis: "falta", ana: "justificada"},
            {rosa: "presente", luis: "presente", ana: "falta"},
            {rosa: "presente", luis: "falta", ana: "presente"},
        ]
    ):
        tomar(c, modulo, estados, fecha=timezone.localdate() - timedelta(days=dias))
    p = porcentajes(modulo)
    assert p[rosa.pk] == {"total": 4, "vino": 3, "pct": 75}
    assert p[luis.pk] == {"total": 4, "vino": 1, "pct": 25}
    assert p[ana.pk] == {"total": 4, "vino": 3, "pct": 75}


def test_el_alumno_ve_su_asistencia(cliente_de, docente, alumnos, modulo):
    rosa, luis, _ana = alumnos
    c = cliente_de(docente)
    tomar(c, modulo, {rosa: "presente", luis: "falta"}, tema="Higiene")
    tomar(c, modulo, {rosa: "tarde", luis: "falta"}, fecha=timezone.localdate() - timedelta(days=1))
    html = cliente_de(rosa).get(reverse(ASIS, args=[modulo.pk])).content.decode()
    assert (
        "Mi asistencia" in html
        and "Viniste a 2 de 2 clases" in html
        and "¡Muy bien!" in html
        and "Higiene" in html
        and "Tarde" in html
    )
    html = cliente_de(luis).get(reverse(ASIS, args=[modulo.pk])).content.decode()
    assert "Viniste a 0 de 2 clases" in html and "Estás faltando mucho" in html
    assert "Guardar asistencia" not in html


def test_alumno_sin_asistencia_registrada(cliente_de, alumnos, modulo):
    assert "Todavía no hay asistencia registrada" in cliente_de(alumnos[0]).get(reverse(ASIS, args=[modulo.pk])).content.decode()


def test_administracion_ve_la_asistencia_pero_no_la_cambia(cliente_de, admin, docente, alumnos, modulo):
    tomar(cliente_de(docente), modulo, {alumnos[0]: "falta", alumnos[1]: "presente"})
    html = cliente_de(admin).get(reverse(ASIS, args=[modulo.pk])).content.decode()
    assert "Faltó" in html and "Vino" in html and "Guardar asistencia" not in html
    ayer = (timezone.localdate() - timedelta(days=1)).isoformat()
    assert "Sin registro" in cliente_de(admin).get(reverse(ASIS, args=[modulo.pk]) + f"?fecha={ayer}").content.decode()
    assert tomar(cliente_de(admin), modulo, {alumnos[0]: "presente"}).status_code == 403


def test_asistencia_solo_para_los_del_modulo(cliente_de, alumno, otro_docente, alumnos, modulo):
    assert cliente_de(alumno).get(reverse(ASIS, args=[modulo.pk])).status_code == 403  # no está en el módulo
    assert cliente_de(otro_docente).get(reverse(ASIS, args=[modulo.pk])).status_code == 403
    assert tomar(cliente_de(otro_docente), modulo, {alumnos[0]: "falta"}).status_code == 403
    assert tomar(cliente_de(alumnos[0]), modulo, {alumnos[0]: "presente"}).status_code == 403
    assert not Asistencia.objects.exists()


def test_inicio_del_docente_marca_la_asistencia_del_dia(cliente_de, docente, alumnos, modulo):
    c = cliente_de(docente)
    html = c.get(reverse("nucleo:inicio")).content.decode()
    assert "Pendiente" in html and "(0 de 3 alumnos)" in html
    tomar(c, modulo, {a: "presente" for a in alumnos})
    html = c.get(reverse("nucleo:inicio")).content.decode()
    assert "Completa" in html and "Ver o corregir la asistencia" in html and "(3 de 3 alumnos)" in html
    assert "ya está tomada" in c.get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    # Llega un alumno nuevo después de tomar la asistencia: queda incompleta
    modulo.matricular(Usuario.objects.create_user(dni="45678912", nombres="Nuevo", password=CLAVE, rol=Rol.ALUMNO))
    html = c.get(reverse("nucleo:inicio")).content.decode()
    assert "Incompleta" in html and "(3 de 4 alumnos)" in html and "Registrar asistencia de hoy" in html


def test_la_lista_de_alumnos_y_el_modulo_muestran_el_porcentaje(cliente_de, docente, alumnos, modulo):
    tomar(cliente_de(docente), modulo, {alumnos[0]: "presente", alumnos[1]: "falta", alumnos[2]: "presente"})
    html = cliente_de(docente).get(reverse("academico:alumnos", args=[modulo.pk])).content.decode()
    assert "100% asistencia" in html and "0% asistencia" in html
    html = cliente_de(alumnos[0]).get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    assert "100% · 1 de 1" in html


def test_asistencia_cuenta_para_eliminar_el_modulo(cliente_de, docente, admin, alumnos, modulo):
    tomar(cliente_de(docente), modulo, {alumnos[0]: "presente"})
    assert "Eliminar módulo" not in cliente_de(docente).get(reverse("academico:modulo", args=[modulo.pk])).content.decode()
    html = cliente_de(admin).get(reverse("academico:admin_eliminar", args=[modulo.pk])).content.decode()
    assert "1 día de asistencia" in html
    cliente_de(admin).post(reverse("academico:admin_eliminar", args=[modulo.pk]), {"entiendo": "1"})
    assert not SesionAsistencia.objects.exists() and not Asistencia.objects.exists()


# ===================================================================== Cálculo de la nota final


def test_redondeo_escolar():
    assert (
        calificacion.redondear(0.25, 1) == 0.3
        and calificacion.redondear(13.45, 1) == 13.5
        and calificacion.redondear(2.5, 0) == 3.0
    )


def test_nota_final_reparte_el_peso_de_lo_que_no_tiene_notas():
    p = Evaluacion(peso_tareas=50, peso_tests=30, peso_asistencia=20)
    assert calificacion.nota_final({"tareas": 16.0, "tests": 12.0, "asistencia": 20.0}, p) == 15.6  # 8 + 3.6 + 4
    assert calificacion.nota_final({"tareas": 16.0, "tests": None, "asistencia": 10.0}, p) == 14.3  # (16*50 + 10*20) / 70
    assert calificacion.nota_final({"tareas": None, "tests": None, "asistencia": None}, p) is None
    assert (
        calificacion.nota_final(
            {"tareas": 10.0, "tests": 20.0, "asistencia": None}, Evaluacion(peso_tareas=100, peso_tests=0, peso_asistencia=0)
        )
        == 10.0
    )


def test_valor_a_mostrar_de_cada_actividad():
    nota = {"tipo_calificacion": "nota", "tipo": "tarea"}
    aprobado = {"tipo_calificacion": "aprobado", "tipo": "tarea"}
    assert calificacion.valor_mostrar(nota, {"nota": 16, "aprobado": None}, False) == (16.0, 16.0)
    assert calificacion.valor_mostrar(nota, None, True) == (0.0, 0.0)  # no entregó y ya venció
    assert calificacion.valor_mostrar(nota, None, False) == ("—", None)
    assert calificacion.valor_mostrar(nota, {"nota": None, "aprobado": None}, True) == ("Por calificar", None)
    assert calificacion.valor_mostrar(
        {"tipo_calificacion": "nota", "tipo": "examen"}, {"nota": None, "aprobado": None}, True
    ) == ("Por revisar", None)
    assert calificacion.valor_mostrar(aprobado, {"nota": None, "aprobado": True}, False) == ("Aprobó", None)
    assert calificacion.valor_mostrar(aprobado, {"nota": None, "aprobado": False}, False) == ("No aprobó", None)
    assert calificacion.valor_mostrar(aprobado, None, True) == ("No entregó", None)


def tarea(clase, titulo, dias=-3, **extra):
    return Tarea.objects.create(clase=clase, titulo=titulo, fecha_limite=timezone.now() + timedelta(days=dias), **extra)


def libro_de(modulo):
    return {a.nombres: a for a in calificacion.libro(modulo)["alumnos"]}


def test_libro_de_notas_con_tareas_y_asistencia(docente, cliente_de, alumnos, modulo, clase):
    rosa, luis, ana = alumnos
    t1, t2 = tarea(clase, "Foto 1", dias=-5), tarea(clase, "Foto 2", dias=-2)
    Entrega.objects.create(tarea=t1, alumno=rosa, nota=Decimal("16"))
    Entrega.objects.create(tarea=t2, alumno=rosa, nota=Decimal("12"))
    Entrega.objects.create(tarea=t1, alumno=luis, nota=Decimal("18"))  # Luis no entregó la 2 y ya venció → 0
    Entrega.objects.create(tarea=t1, alumno=ana)  # entregó y espera nota: no cuenta todavía
    tomar(cliente_de(docente), modulo, {rosa: "presente", luis: "falta", ana: "presente"})
    libro = libro_de(modulo)
    assert libro["Rosa"].notas == {f"t{t1.pk}": 16.0, f"t{t2.pk}": 12.0}
    assert (
        libro["Rosa"].partes == {"tareas": 14.0, "tests": None, "asistencia": 20.0} and libro["Rosa"].promedio == 15.7
    )  # (14*50 + 20*20)/70
    assert libro["Luis"].notas == {f"t{t1.pk}": 18.0, f"t{t2.pk}": 0.0}
    assert (
        libro["Luis"].partes["tareas"] == 9.0 and libro["Luis"].partes["asistencia"] == 0.0 and libro["Luis"].promedio == 6.4
    )  # (9*50 + 0)/70
    assert libro["Ana"].notas == {f"t{t1.pk}": "Por calificar", f"t{t2.pk}": 0.0}
    assert libro["Ana"].partes["tareas"] == 0.0  # solo cuenta el 0 de la tarea que no entregó
    assert libro["Rosa"].situacion == "Aprobado" and libro["Luis"].situacion == "Desaprobado" and libro["Luis"].bajo


def test_la_asistencia_sola_no_da_nota(docente, cliente_de, alumnos, modulo):
    tomar(cliente_de(docente), modulo, {a: "presente" for a in alumnos})
    assert all(a.promedio is None for a in calificacion.libro(modulo)["alumnos"])


def test_tarea_aprobo_no_aprobo_no_entra_al_promedio(alumnos, modulo, clase):
    rosa = alumnos[0]
    t = tarea(clase, "Práctica", tipo_calificacion="aprobado")
    Entrega.objects.create(tarea=t, alumno=rosa, aprobado=True)
    a = libro_de(modulo)["Rosa"]
    assert a.notas == {f"t{t.pk}": "Aprobó"} and a.promedio is None


def test_cambiar_los_pesos_cambia_la_nota(alumnos, modulo, clase):
    rosa = alumnos[0]
    Entrega.objects.create(tarea=tarea(clase, "Foto"), alumno=rosa, nota=Decimal("14"))
    assert libro_de(modulo)["Rosa"].promedio == 14.0
    Evaluacion.objects.create(modulo=modulo, peso_tareas=100, peso_tests=0, peso_asistencia=0, nota_minima=Decimal("13"))
    a = libro_de(modulo)["Rosa"]
    assert a.promedio == 14.0 and calificacion.libro(modulo)["minima"] == 13.0 and a.situacion == "Aprobado"


def test_el_alumno_no_ve_actividades_de_clases_que_no_empiezan(alumnos, modulo):
    rosa = alumnos[0]
    futura = Clase.crear(modulo, "Futura", inicio=date.today() + timedelta(days=9))
    t = tarea(futura, "Secreta", dias=20)
    resumen = calificacion.del_alumno(modulo, rosa)
    assert resumen["filas"] == [] and t


# ===================================================================== Pantallas de notas


def test_libro_de_notas_del_docente(cliente_de, docente, alumnos, modulo, clase):
    rosa = alumnos[0]
    t = tarea(clase, "Foto del corte degrafilado final", dias=-2)
    Entrega.objects.create(tarea=t, alumno=rosa, nota=Decimal("16.5"))
    html = cliente_de(docente).get(reverse("evaluacion:notas_modulo", args=[modulo.pk])).content.decode()
    assert (
        "Notas y reportes" in html and "Quispe, Rosa" in html and "16.5" in html and "Aprobado" in html and "Desaprobado" in html
    )
    assert "Foto del corte de…" in html and "Descargar para Excel" in html and "Imprimir o guardar PDF" in html
    assert "trabajos 50% + tests 30% + asistencia 20%" in html and "Se aprueba con 11" in html and "Guardar" in html


def test_libro_de_notas_sin_alumnos(cliente_de, docente, modulo):
    html = cliente_de(docente).get(reverse("evaluacion:notas_modulo", args=[modulo.pk])).content.decode()
    assert "Este módulo todavía no tiene alumnos" in html


def test_administracion_ve_el_libro_sin_poder_cambiar_los_pesos(cliente_de, admin, alumnos, modulo):
    html = cliente_de(admin).get(reverse("evaluacion:notas_modulo", args=[modulo.pk])).content.decode()
    assert "Quispe, Rosa" in html and 'name="peso_tareas"' not in html
    assert cliente_de(admin).post(reverse("evaluacion:notas_pesos", args=[modulo.pk]), {"peso_tareas": "100"}).status_code == 403


def test_el_docente_cambia_los_pesos(cliente_de, docente, alumnos, modulo):
    c = cliente_de(docente)
    r = c.post(
        reverse("evaluacion:notas_pesos", args=[modulo.pk]),
        {"peso_tareas": "60", "peso_tests": "20", "peso_asistencia": "20", "nota_minima": "12,5"},
    )
    assert r["Location"] == reverse("evaluacion:notas_modulo", args=[modulo.pk])
    ev = Evaluacion.objects.get()
    assert (ev.peso_tareas, ev.peso_tests, ev.peso_asistencia, ev.nota_minima) == (60, 20, 20, Decimal("12.50"))
    html = c.get(r["Location"]).content.decode()
    assert (
        "trabajos 60% + tests 20% + asistencia 20%" in html
        and "Se aprueba con 12.5" in html
        and "Listo: la nota final se calcula con trabajos 60%" in html
    )


@pytest.mark.parametrize(
    ("datos", "texto"),
    [
        (
            {"peso_tareas": "50", "peso_tests": "30", "peso_asistencia": "30", "nota_minima": "11"},
            "deben sumar 100. Ahora suman 110",
        ),
        ({"peso_tareas": "-10", "peso_tests": "60", "peso_asistencia": "50", "nota_minima": "11"}, "deben sumar 100"),
        ({"peso_tareas": "x", "peso_tests": "30", "peso_asistencia": "20", "nota_minima": "11"}, "deben sumar 100"),
        ({"peso_tareas": "50", "peso_tests": "30", "peso_asistencia": "20", "nota_minima": "25"}, "entre 0 y 20"),
        ({"peso_tareas": "50", "peso_tests": "30", "peso_asistencia": "20", "nota_minima": "abc"}, "entre 0 y 20"),
    ],
)
def test_pesos_con_errores(cliente_de, docente, modulo, datos, texto):
    c = cliente_de(docente)
    r = c.post(reverse("evaluacion:notas_pesos", args=[modulo.pk]), datos)
    assert texto in c.get(r["Location"].split("#")[0]).content.decode() and not Evaluacion.objects.exists()


def test_solo_el_docente_del_modulo_cambia_los_pesos(cliente_de, alumnos, otro_docente, modulo):
    datos = {"peso_tareas": "100", "peso_tests": "0", "peso_asistencia": "0", "nota_minima": "11"}
    for p in (alumnos[0], otro_docente):
        assert cliente_de(p).post(reverse("evaluacion:notas_pesos", args=[modulo.pk]), datos).status_code == 403


def test_mis_notas_del_alumno(cliente_de, docente, alumnos, modulo, clase):
    rosa = alumnos[0]
    t1, t2 = tarea(clase, "Foto 1", dias=-5), tarea(clase, "Foto 2", dias=5)
    Entrega.objects.create(tarea=t1, alumno=rosa, nota=Decimal("16"), comentario_docente="Muy bien", calificado=timezone.now())
    c = cliente_de(rosa)
    html = c.get(reverse("evaluacion:mis_notas")).content.decode()
    assert "Mis notas" in html and "Peluquería – M1" in html and "Calificado recientemente" in html and "Foto 1" in html
    assert (
        "16" in html and "Muy bien" in html and "Por entregar" in html and "Se aprueba con 11" in html and "Vas aprobando" in html
    )
    assert "Prof. María Torres" in html and t2
    html = c.get(reverse("evaluacion:notas_modulo", args=[modulo.pk])).content.decode()
    assert "Contenido" in html and "Calificaciones" in html and '<details class="nota-todo" open>' in html


def test_mis_notas_sin_modulos(cliente_de, alumno):
    html = cliente_de(alumno).get(reverse("evaluacion:mis_notas")).content.decode()
    assert "Todavía no estás en ningún módulo" in html


def test_mis_notas_es_solo_para_alumnos(cliente_de, docente, admin):
    for p in (docente, admin):
        assert cliente_de(p).get(reverse("evaluacion:mis_notas")).status_code == 403


def test_un_alumno_no_ve_las_notas_de_otro_modulo(cliente_de, alumno, modulo):
    assert cliente_de(alumno).get(reverse("evaluacion:notas_modulo", args=[modulo.pk])).status_code == 403


# ===================================================================== Excel e impresión


def test_descargar_para_excel(cliente_de, docente, alumnos, modulo, clase):
    rosa, luis, _ana = alumnos
    t = tarea(clase, "Foto del corte", dias=-2)
    Entrega.objects.create(tarea=t, alumno=rosa, nota=Decimal("16.5"))
    luis.apellidos = "=CMD|' /C calc'!A0"  # un nombre malicioso no se convierte en fórmula
    luis.save()
    tomar(cliente_de(docente), modulo, {rosa: "presente", luis: "falta"})
    r = cliente_de(docente).get(reverse("evaluacion:notas_excel", args=[modulo.pk]))
    assert r["Content-Type"] == "text/csv; charset=utf-8" and r["X-Content-Type-Options"] == "nosniff"
    assert r["Content-Disposition"] == f'attachment; filename="notas-peluqueria-m1-{timezone.localdate().isoformat()}.csv"'
    texto = r.content.decode("utf-8")
    assert texto.startswith("﻿")
    lineas = texto.lstrip("﻿").splitlines()
    assert lineas[0] == "CETPRO Mangomarca - Peluquería – M1"
    assert lineas[1].startswith("Docente: María Torres;Periodo: 2026-II;Turno: mañana;Fecha: ")
    assert (
        lineas[3]
        == "N°;DNI;Apellidos;Nombres;Foto del corte;Trabajos (50%);Tests (30%);Asistencia (20%);Nota final;Asistencia %;Situación"
    )
    fila_rosa = next(x for x in lineas if "Quispe" in x)
    assert fila_rosa == "2;40000000;Quispe;Rosa;16,5;16,5;;20;17,5;100;Aprobado"  # (16,5×50 + 20×20) / 70 = 17,5
    fila_luis = next(x for x in lineas if "Luis" in x)
    assert fila_luis == "1;40000001;'=CMD|' /C calc'!A0;Luis;0;0;;0;0;0;Desaprobado"  # el apóstrofo evita que sea una fórmula


def test_excel_solo_para_docente_y_administracion(cliente_de, alumnos, otro_docente, admin, modulo):
    assert cliente_de(alumnos[0]).get(reverse("evaluacion:notas_excel", args=[modulo.pk])).status_code == 403
    assert cliente_de(otro_docente).get(reverse("evaluacion:notas_excel", args=[modulo.pk])).status_code == 403
    assert cliente_de(admin).get(reverse("evaluacion:notas_excel", args=[modulo.pk])).status_code == 200


def test_version_para_imprimir(cliente_de, docente, alumnos, modulo, clase):
    Entrega.objects.create(tarea=tarea(clase, "Foto"), alumno=alumnos[0], nota=Decimal("8"))
    html = cliente_de(docente).get(reverse("evaluacion:notas_imprimir", args=[modulo.pk])).content.decode()
    assert (
        "CETPRO Mangomarca — Registro de notas" in html
        and "Quispe, Rosa" in html
        and 'class="n bajo"' in html
        and "Imprimir o guardar como PDF" in html
    )
    assert cliente_de(alumnos[0]).get(reverse("evaluacion:notas_imprimir", args=[modulo.pk])).status_code == 403


# ===================================================================== Registro consolidado


def test_registro_consolidado(cliente_de, admin, docente, alumnos, modulo, clase):
    Entrega.objects.create(tarea=tarea(clase, "Foto"), alumno=alumnos[0], nota=Decimal("15"))
    otro = Modulo.crear(nombre="Otro", especialidad="Soldadura Universal", periodo="2025-II", turno="noche", docente=docente)
    otro.matricular(alumnos[1])
    c = cliente_de(admin)
    html = c.get(reverse("nucleo:inicio")).content.decode()
    assert (
        "Registro consolidado" in html and "Exportar registro consolidado (Excel)" in html and "<option>2025-II</option>" in html
    )
    r = c.get(reverse("evaluacion:consolidado"))
    assert r["Content-Disposition"] == f'attachment; filename="registro-consolidado-{timezone.localdate().isoformat()}.csv"'
    lineas = r.content.decode().lstrip("﻿").splitlines()
    assert lineas[0] == "CETPRO Mangomarca - Registro consolidado" and lineas[1].endswith("Todos los módulos activos")
    assert lineas[3] == "Periodo;Curso;Módulo;Turno;Docente;DNI;Apellidos;Nombres;Asistencia;Nota final;Condición"
    assert "2026-II;Peluquería y Barbería;Peluquería – M1;mañana;María Torres;40000000;Quispe;Rosa;;15;Aprobado" in lineas
    assert any(x.startswith("2025-II;Soldadura Universal;Otro") and x.endswith("Sin nota") for x in lineas)
    assert Registro.objects.filter(accion="notas", detalle__contains="exportó el registro consolidado").exists()
    lineas = c.get(reverse("evaluacion:consolidado") + "?periodo=2025-II").content.decode().lstrip("﻿").splitlines()
    assert lineas[1].endswith("Periodo: 2025-II") and not any("Peluquería – M1" in x for x in lineas)


def test_consolidado_tambien_para_direccion_y_no_para_los_demas(cliente_de, docente, alumno):
    direccion = Usuario.objects.create_user(correo="dir@cetpro.com", nombres="Dora", password=CLAVE, rol=Rol.DIRECCION)
    assert cliente_de(direccion).get(reverse("evaluacion:consolidado")).status_code == 200
    for p in (docente, alumno):
        assert cliente_de(p).get(reverse("evaluacion:consolidado")).status_code == 403


def test_reportes_del_inicio_de_administracion(cliente_de, admin, docente, alumnos, modulo, clase):
    rosa, luis, _ana = alumnos
    t = tarea(clase, "Foto", dias=-2)
    Entrega.objects.create(tarea=t, alumno=rosa, nota=Decimal("15"))
    Entrega.objects.create(tarea=t, alumno=luis)
    tomar(cliente_de(docente), modulo, {rosa: "presente", luis: "falta", alumnos[2]: "presente"})
    html = cliente_de(admin).get(reverse("nucleo:inicio")).content.decode()
    assert "67<small>%</small>" in html  # 2 de 3 vinieron
    assert "De 3 asistencias registradas en 1 clase" in html
    assert '1</div><div class="texto-2 small fw-bold">calificadas' in html and "50% de lo entregado ya tiene nota" in html
    assert "Calificación al día, por módulo" in html and "Peluquería – M1" in html and "María Torres" in html
