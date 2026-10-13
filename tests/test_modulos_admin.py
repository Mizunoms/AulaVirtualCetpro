"""Administración de cursos y módulos: catálogo, crear, editar, archivar, eliminar, alumnos y accesos."""

import pytest
from django.urls import reverse

from apps.academico.models import Matricula, Modulo, UnidadDidactica
from apps.cuentas.models import Rol, Usuario
from apps.nucleo.models import Registro

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


def datos_formulario(docente, **cambios):
    base = {
        "especialidad": "Soporte Técnico",
        "modulo": "Módulo 1",
        "nombre": "",
        "periodo": "2026-II",
        "turno": "tarde",
        "horario": "Lunes a viernes",
        "docente_id": str(docente.pk),
    }
    return {**base, **cambios}


# ---------- El modelo ----------


def test_codigo_de_inscripcion(modulo):
    assert len(modulo.codigo) == 7 and modulo.codigo[:3] == "SOP" and modulo.codigo[3:].isdigit()
    assert modulo.codigo_fmt == f"SOP-{modulo.codigo[3:]}"
    modulo.nuevo_codigo()  # el código nuevo siempre es válido (puede coincidir con el anterior por azar)
    assert len(modulo.codigo) == 7 and modulo.codigo[:3] == "SOP"
    assert Modulo.por_codigo(modulo.codigo_fmt.lower()) == modulo
    assert Modulo.por_codigo(modulo.codigo.replace("SOP", "SOP ")) == modulo
    assert Modulo.por_codigo("XYZ1234") is None and Modulo.por_codigo("hola") is None


def test_codigo_ignora_tildes_y_modulos_archivados(docente):
    m = Modulo.crear(nombre="x", especialidad="Panadería y Pastelería", periodo="2026-II", turno="tarde", docente=docente)
    assert m.codigo.startswith("PAN")
    m.activo = False
    m.save()
    assert Modulo.por_codigo(m.codigo) is None


def test_matricular_no_repite(modulo, alumno):
    assert modulo.matricular(alumno) is True
    assert modulo.matricular(alumno) is False
    assert Matricula.objects.filter(modulo=modulo).count() == 1
    assert modulo.es_alumno(alumno) and list(modulo.alumnos()) == [alumno]


# ---------- Solo el administrador ----------


def test_solo_el_admin_entra(cliente_de, alumno, docente, client):
    for nombre in ("admin_cursos", "admin_modulos", "admin_nuevo"):
        assert client.get(reverse(f"academico:{nombre}")).status_code == 302
        for p in (alumno, docente):
            assert cliente_de(p).get(reverse(f"academico:{nombre}")).status_code == 403


# ---------- Cursos y catálogo ----------


def test_cursos_con_sus_modulos(cliente_de, admin, modulo):
    html = cliente_de(admin).get(reverse("academico:admin_cursos")).content.decode()
    assert "Soporte Técnico" in html and "Soporte – Módulo 1" in html and "Peluquería y Barbería" in html
    assert "1 módulo" in html


def test_catalogo_de_modulos_y_filtros(cliente_de, admin, modulo, docente):
    otro = Modulo.crear(
        nombre="Peluquería – M1", especialidad="Peluquería y Barbería", periodo="2026-I", turno="mañana", docente=docente
    )
    c = cliente_de(admin)
    html = c.get(reverse("academico:admin_modulos")).content.decode()
    assert "Soporte – Módulo 1" in html and "Peluquería – M1" in html and "Activos (2)" in html
    html = c.get(reverse("academico:admin_modulos") + "?especialidad=Peluquería y Barbería").content.decode()
    assert "Peluquería – M1" in html and "Soporte – Módulo 1" not in html
    html = c.get(reverse("academico:admin_modulos") + "?q=" + modulo.codigo_fmt).content.decode()
    assert "Soporte – Módulo 1" in html and "Peluquería – M1" not in html
    html = c.get(reverse("academico:admin_modulos") + "?q=torres").content.decode()  # busca por docente
    assert "Soporte – Módulo 1" in html and "Peluquería – M1" in html
    html = c.get(reverse("academico:admin_modulos") + "?periodo=2026-I").content.decode()
    assert "Peluquería – M1" in html and "Soporte – Módulo 1" not in html
    otro.activo = False
    otro.save()
    assert "Peluquería – M1" in c.get(reverse("academico:admin_modulos") + "?estado=archivados").content.decode()
    assert "No hay módulos archivados" in c.get(reverse("academico:admin_modulos") + "?estado=archivados&q=zzz").content.decode()


# ---------- Crear y editar ----------


def test_crear_modulo_con_unidades_didacticas(cliente_de, admin, docente):
    c = cliente_de(admin)
    assert "Soporte Técnico" in c.get(reverse("academico:admin_nuevo") + "?especialidad=Soporte Técnico").content.decode()
    datos = datos_formulario(docente, nombre="")
    datos["ud_nombre[]"] = ["Seguridad informática", "", "Redes"]
    datos["ud_creditos[]"] = ["2", "", "4"]
    datos["ud_horas[]"] = ["48", "", "96"]
    r = c.post(reverse("academico:admin_modulos"), datos)
    m = Modulo.objects.get()
    assert r["Location"] == reverse("academico:admin_alumnos", args=[m.pk])
    assert m.nombre == "Soporte Técnico – Módulo 1" and m.turno == "tarde" and m.codigo
    unidades = list(m.unidades_didacticas.all())
    assert [(u.nombre, u.creditos, u.horas) for u in unidades] == [("Seguridad informática", 2, 48), ("Redes", 4, 96)]
    assert UnidadDidactica.totales(unidades) == (6, 144)


@pytest.mark.parametrize(
    ("cambio", "texto"),
    [
        ({"especialidad": "Inventada"}, "Elige el curso, el módulo, el periodo y el turno"),
        ({"turno": ""}, "Elige el curso, el módulo, el periodo y el turno"),
        ({"periodo": ""}, "Elige el curso, el módulo, el periodo y el turno"),
        ({"docente_id": ""}, "Elige el docente del módulo"),
    ],
)
def test_crear_modulo_con_errores(cliente_de, admin, docente, cambio, texto):
    c = cliente_de(admin)
    r = c.post(reverse("academico:admin_modulos"), datos_formulario(docente, **cambio))
    assert r["Location"] == reverse("academico:admin_nuevo")
    assert texto in c.get(r["Location"]).content.decode()
    assert not Modulo.objects.exists()


def test_unidades_didacticas_con_error_se_conservan_en_el_formulario(cliente_de, admin, docente):
    c = cliente_de(admin)
    datos = datos_formulario(docente)
    datos["ud_nombre[]"] = ["Primera", "Segunda"]
    datos["ud_creditos[]"] = ["99", ""]
    datos["ud_horas[]"] = ["", ""]
    r = c.post(reverse("academico:admin_modulos"), datos)
    html = c.get(r["Location"]).content.decode()
    assert "los créditos van de 0 a 40" in html and 'value="Primera"' in html and 'value="Segunda"' in html


def test_solo_un_docente_puede_dictar(cliente_de, admin, alumno):
    c = cliente_de(admin)
    r = c.post(reverse("academico:admin_modulos"), datos_formulario(alumno))
    assert not Modulo.objects.exists() and "Elige el docente" in c.get(r["Location"]).content.decode()


def test_editar_modulo(cliente_de, admin, modulo, docente):
    c = cliente_de(admin)
    html = c.get(reverse("academico:admin_editar", args=[modulo.pk])).content.decode()
    assert "Editar módulo" in html and "Módulo activo" in html
    datos = datos_formulario(docente, nombre="Nombre nuevo", turno="mañana", periodo="2027-I")
    datos["activo"] = "1"
    r = c.post(reverse("academico:admin_actualizar", args=[modulo.pk]), datos)
    assert r["Location"] == reverse("academico:admin_modulos")
    modulo.refresh_from_db()
    assert (modulo.nombre, modulo.turno, modulo.periodo, modulo.activo) == ("Nombre nuevo", "mañana", "2027-I", True)
    del datos["activo"]
    c.post(reverse("academico:admin_actualizar", args=[modulo.pk]), datos)
    modulo.refresh_from_db()
    assert modulo.activo is False


# ---------- Archivar ----------


def test_archivar_y_reactivar_uno(cliente_de, admin, modulo):
    c = cliente_de(admin)
    c.post(reverse("academico:admin_estado", args=[modulo.pk]), {"volver": "?estado=todos"})
    modulo.refresh_from_db()
    assert modulo.activo is False
    r = c.post(reverse("academico:admin_estado", args=[modulo.pk]), {"volver": "?estado=todos"})
    assert r["Location"] == reverse("academico:admin_modulos") + "?estado=todos"
    modulo.refresh_from_db()
    assert modulo.activo is True
    assert Registro.objects.filter(accion="modulo", detalle__contains="archivó").exists()


def test_volver_solo_a_filtros_de_la_lista(cliente_de, admin, modulo):
    r = cliente_de(admin).post(reverse("academico:admin_estado", args=[modulo.pk]), {"volver": "https://malo.com"})
    assert r["Location"] == reverse("academico:admin_modulos")


def test_archivar_en_bloque_y_por_periodo(cliente_de, admin, modulo, docente):
    otro = Modulo.crear(nombre="O", especialidad="Soporte Técnico", periodo="2026-I", turno="tarde", docente=docente)
    c = cliente_de(admin)
    r = c.post(reverse("academico:admin_lote"), {"accion": "archivar", "ids[]": [str(modulo.pk), str(otro.pk)]})
    assert r.status_code == 302
    assert Modulo.objects.filter(activo=True).count() == 0
    c.post(reverse("academico:admin_lote"), {"accion": "reactivar", "ids[]": [str(otro.pk)]})
    assert list(Modulo.objects.filter(activo=True)) == [otro]
    c.post(reverse("academico:admin_lote"), {"accion": "archivar_periodo", "periodo": "2026-I"})
    assert Modulo.objects.filter(activo=True).count() == 0
    r = c.post(reverse("academico:admin_lote"), {"accion": "archivar"})
    assert "Marca primero los módulos" in c.get(r["Location"]).content.decode()
    r = c.post(reverse("academico:admin_lote"), {"accion": "", "ids[]": [str(modulo.pk)]})
    assert "Elige qué quieres hacer" in c.get(r["Location"]).content.decode()


# ---------- Eliminar de verdad ----------


def test_eliminar_modulo_vacio(cliente_de, admin, modulo):
    c = cliente_de(admin)
    html = c.get(reverse("academico:admin_eliminar", args=[modulo.pk])).content.decode()
    assert "Esto no se puede deshacer" in html and "Está vacío" in html and 'name="entiendo"' not in html
    r = c.post(reverse("academico:admin_eliminar", args=[modulo.pk]))
    assert r["Location"] == reverse("academico:admin_modulos") and not Modulo.objects.exists()


def test_eliminar_modulo_con_alumnos_pide_entiendo_y_borra_todo(cliente_de, admin, modulo, alumno):
    modulo.matricular(alumno)
    from apps.academico.models import Clase

    Clase.crear(modulo, "Clase 1")
    c = cliente_de(admin)
    html = c.get(reverse("academico:admin_eliminar", args=[modulo.pk])).content.decode()
    assert "1 alumno inscrito" in html and "1 clase" in html and 'name="entiendo"' in html
    r = c.post(reverse("academico:admin_eliminar", args=[modulo.pk]))
    assert "Marca la casilla «Entiendo»" in c.get(r["Location"]).content.decode()
    assert Modulo.objects.exists()
    c.post(reverse("academico:admin_eliminar", args=[modulo.pk]), {"entiendo": "1"})
    assert not Modulo.objects.exists() and not Matricula.objects.exists() and not Clase.objects.exists()
    assert Usuario.objects.filter(pk=alumno.pk).exists()  # el alumno sigue existiendo
    assert Registro.objects.filter(accion="modulo", detalle__contains="Se borró también: 1 alumno inscrito, 1 clase").exists()


# ---------- Alumnos del módulo ----------


def test_agregar_alumnos_con_una_lista(cliente_de, admin, modulo, alumno):
    c = cliente_de(admin)
    lista = "12345678\n45678912, Ana María, Quispe Rojas\n\n123\n99999999\n"
    r = c.post(reverse("academico:admin_alumnos", args=[modulo.pk]), {"lista": lista})
    html = c.get(r["Location"]).content.decode()
    assert "2 alumnos agregados" in html and "1 nuevo: creará" in html
    assert "Línea 4: escribe un DNI de 8 números" in html and "Línea 5: el DNI 99999999 no tiene cuenta" in html
    nuevo = Usuario.objects.get(dni="45678912")
    assert nuevo.pendiente and nuevo.rol == Rol.ALUMNO and nuevo.origen == "lista" and nuevo.apellidos == "Quispe Rojas"
    assert set(modulo.alumnos()) == {alumno, nuevo}
    # Repetir no duplica
    html = c.get(c.post(reverse("academico:admin_alumnos", args=[modulo.pk]), {"lista": "12345678"})["Location"]).content.decode()
    assert "0 alumnos agregados" in html


def test_lista_con_dni_de_docente_no_vale(cliente_de, admin, modulo):
    c = cliente_de(admin)
    Usuario.objects.create_user(dni="55555555", nombres="Prof", rol=Rol.DOCENTE, password=CLAVE)
    r = c.post(reverse("academico:admin_alumnos", args=[modulo.pk]), {"lista": "55555555"})
    assert "no es de un alumno" in c.get(r["Location"]).content.decode()
    assert not Matricula.objects.exists()


def test_pantalla_de_alumnos_y_quitar(cliente_de, admin, modulo, alumno):
    modulo.matricular(alumno)
    c = cliente_de(admin)
    html = c.get(reverse("academico:admin_alumnos", args=[modulo.pk])).content.decode()
    assert modulo.codigo_fmt in html and "Quispe Mamani, Rosa" in html and "Preparar accesos" in html
    c.post(reverse("academico:admin_quitar", args=[modulo.pk, alumno.pk]))
    assert not Matricula.objects.exists()


def test_preparar_accesos_da_claves_temporales_y_se_ven_una_sola_vez(cliente_de, admin, modulo, alumno):
    pendiente = Usuario.objects.crear_alumno("45678912", "Ana", "Rojas", telefono="987654321")
    listo = Usuario.objects.create_user(dni="22222222", nombres="Ya", password=CLAVE, rol=Rol.ALUMNO)
    alumno.debe_cambiar_clave = True  # tiene una temporal que todavía no cambió
    alumno.save()
    for a in (alumno, pendiente, listo):
        modulo.matricular(a)
    c = cliente_de(admin)
    r = c.post(reverse("academico:admin_accesos", args=[modulo.pk]))
    assert r["Location"] == reverse("cuentas:admin_claves")
    html = c.get(r["Location"]).content.decode()
    assert "2 contraseñas nuevas creadas" in html and "Ana Rojas" in html and "https://wa.me/51987654321?text=" in html
    assert "Ya" not in html.split("tabla-claves")[1].split("</table>")[0].replace(
        "Ya pasó", ""
    )  # a quien ya eligió no se le toca
    pendiente.refresh_from_db()
    alumno.refresh_from_db()
    assert not pendiente.pendiente and pendiente.debe_cambiar_clave and alumno.debe_cambiar_clave
    assert not alumno.check_password(CLAVE)  # la anterior dejó de servir
    listo.refresh_from_db()
    assert listo.check_password(CLAVE) and not listo.debe_cambiar_clave
    # Solo se muestran una vez
    r2 = c.get(reverse("cuentas:admin_claves"))
    assert r2.status_code == 302
    assert Registro.objects.filter(accion="clave", detalle__contains="preparó los accesos de 2 alumnos").exists()


def test_accesos_cuando_todos_ya_eligieron(cliente_de, admin, modulo, alumno):
    modulo.matricular(alumno)
    c = cliente_de(admin)
    r = c.post(reverse("academico:admin_accesos", args=[modulo.pk]))
    assert "ya eligieron su contraseña" in c.get(r["Location"]).content.decode()


# ---------- Cursos (especialidades) en Ajustes ----------


def test_renombrar_curso_cambia_sus_modulos(cliente_de, admin, modulo):
    c = cliente_de(admin)
    html = c.get(reverse("nucleo:ajustes") + "?tab=especialidades").content.decode()
    assert "Cursos (programas de estudios)" in html and "1 módulo" in html
    datos = {}
    from apps.nucleo import ajustes

    for i, e in enumerate(ajustes.especialidades()):
        datos |= {f"nombre[{i}]": e["nombre"], f"original[{i}]": e["nombre"], f"color[{i}]": e["color"]}
    datos["nombre[0]"] = "Soporte y Redes"
    r = c.post(reverse("nucleo:ajustes_especialidades"), datos)
    assert r.status_code == 302
    modulo.refresh_from_db()
    assert modulo.especialidad == "Soporte y Redes"


def test_no_se_quita_un_curso_con_modulos(cliente_de, admin, modulo):
    from apps.nucleo import ajustes

    datos = {}
    for i, e in enumerate(ajustes.especialidades()):
        datos |= {f"nombre[{i}]": e["nombre"], f"original[{i}]": e["nombre"], f"color[{i}]": e["color"]}
    datos["quitar[0]"] = "1"
    c = cliente_de(admin)
    r = c.post(reverse("nucleo:ajustes_especialidades"), datos)
    assert "tiene módulos: no se puede quitar" in c.get(r["Location"]).content.decode()
    assert any(e["nombre"] == "Soporte Técnico" for e in ajustes.especialidades())


def test_agregar_un_curso_nuevo(cliente_de, admin):
    from apps.nucleo import ajustes

    datos = {}
    n = len(ajustes.especialidades())
    for i, e in enumerate(ajustes.especialidades()):
        datos |= {f"nombre[{i}]": e["nombre"], f"original[{i}]": e["nombre"], f"color[{i}]": e["color"]}
    datos |= {f"nombre[{n}]": "Electricidad", f"original[{n}]": "", f"color[{n}]": "#166534"}
    c = cliente_de(admin)
    c.post(reverse("nucleo:ajustes_especialidades"), datos)
    assert "Electricidad" in [e["nombre"] for e in ajustes.especialidades()]
    datos[f"color[{n}]"] = "#FFFF00"
    r = c.post(reverse("nucleo:ajustes_especialidades"), datos)
    assert "muy claro" in c.get(r["Location"]).content.decode()
