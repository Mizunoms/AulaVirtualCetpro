"""Panel de Personas del administrador: lista, crear, editar, contraseñas, activar o desactivar y eliminar de verdad."""

from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.academico.models import Aviso, Clase, Matricula, Modulo, PreguntaClase
from apps.cuentas.models import Origen, Rol, Usuario
from apps.evaluacion.models import Asistencia, SesionAsistencia
from apps.formularios.models import Intento
from apps.mensajes.models import Conversacion, Mensaje
from apps.nucleo import archivos
from apps.nucleo.models import Registro
from apps.tareas.models import Entrega, Tarea

from . import muestras
from .conftest import CLAVE
from .formularios_comun import nuevo_formulario, pregunta

pytestmark = pytest.mark.django_db

LISTA = "cuentas:admin_personas"


@pytest.fixture
def modulo(docente):
    return Modulo.crear(
        nombre="Peluquería – M1",
        especialidad="Peluquería y Barbería",
        modulo="Módulo 1",
        periodo="2026-II",
        turno="mañana",
        docente=docente,
    )


@pytest.fixture
def modulo_2(docente):
    return Modulo.crear(
        nombre="Panadería – M1",
        especialidad="Panadería y Pastelería",
        modulo="Módulo 1",
        periodo="2026-II",
        turno="noche",
        docente=docente,
    )


@pytest.fixture
def clase(modulo):
    return Clase.crear(modulo, "Corte básico")


def alumno_de(dni, nombres="Luis", apellidos="Paz", **extra):
    return Usuario.objects.create_user(dni=dni, nombres=nombres, apellidos=apellidos, password=CLAVE, rol=Rol.ALUMNO, **extra)


def datos(**cambio):
    base = {
        "rol": "docente",
        "nombres": "Pedro",
        "apellidos": "Rojas Vega",
        "correo": "pedro@cetpro.com",
        "dni": "",
        "telefono": "",
        "forzar_cambio": "1",
    }
    base.update(cambio)
    return {k: v for k, v in base.items() if v is not None}  # None = la casilla no se marcó


# ===================================================================== La lista


def test_solo_el_administrador_ve_las_personas(cliente_de, docente, alumno, admin):
    for quien in (docente, alumno):
        assert cliente_de(quien).get(reverse(LISTA)).status_code == 403
    assert Client().get(reverse(LISTA))["Location"] == reverse("cuentas:login")
    assert cliente_de(admin).get(reverse(LISTA)).status_code == 200


def test_la_lista_muestra_a_las_personas(cliente_de, admin, docente, alumno, modulo):
    modulo.matricular(alumno)
    html = cliente_de(admin).get(reverse(LISTA)).content.decode()
    assert "Personas" in html and "Nuevo docente" in html and "Nuevo alumno" in html and "Cargar lista de alumnos" in html
    assert "Quispe Mamani, Rosa" in html and "DNI 12345678" in html and "Torres, María" in html and "maria@cetpro.com" in html
    assert "Todos (3)" in html and "Docentes (1)" in html and "Alumnos (1)" in html and "Dirección y admin (1)" in html
    assert "Peluquería y Barbería" in html and "Módulo 1" in html and "Mostrando 1–3 de 3 personas" in html
    assert "Directora" in html and f'value="{admin.pk}" form="lote"' not in html  # uno mismo no se marca
    assert f'value="{alumno.pk}" form="lote"' in html


def test_estados_en_la_lista(cliente_de, admin, docente):
    inactivo = alumno_de("40000001", "Inés", "Díaz")
    inactivo.is_active = False
    inactivo.save()
    alumno_de("40000002", "Ana", "Pérez").set_password("x")
    pendiente = Usuario.objects.crear_alumno("40000003", "Pepe", "Soto")
    temporal = alumno_de("40000004", "Tere", "Vera", debe_cambiar_clave=True)
    html = cliente_de(admin).get(reverse(LISTA)).content.decode()
    assert "Inactivo" in html and "Sin contraseña aún" in html and "Debe cambiar su clave" in html and 'chip-ok">Activo' in html
    assert pendiente.pendiente and temporal.debe_cambiar_clave


def test_pestanas_de_la_lista(cliente_de, admin, docente, alumno):
    inactivo = alumno_de("40000001", "Inés", "Díaz")
    Usuario.objects.filter(pk=inactivo.pk).update(is_active=False)
    Usuario.objects.crear_alumno("40000003", "Pepe", "Soto")
    c = cliente_de(admin)
    aparece = lambda rol, nombre: nombre in c.get(reverse(LISTA) + f"?rol={rol}").content.decode()  # noqa: E731
    assert aparece("docente", "Torres, María") and not aparece("docente", "Quispe Mamani")
    assert aparece("alumno", "Quispe Mamani") and not aparece("alumno", "Torres, María")
    assert aparece("personal", "Directora") and not aparece("personal", "Quispe")
    assert aparece("pendientes", "Soto, Pepe") and not aparece("pendientes", "Quispe Mamani")
    assert aparece("inactivos", "Díaz, Inés") and not aparece("inactivos", "Soto")
    assert aparece("admin", "Directora") and not aparece("admin", "Torres")
    assert aparece("rol-que-no-existe", "Torres, María")  # un grupo desconocido muestra a todos
    pendientes = c.get(reverse(LISTA) + "?rol=pendientes").content.decode()
    assert 'aria-current="page">Sin contraseña (1)' in pendientes


def test_buscar_personas(cliente_de, admin, docente, alumno):
    c = cliente_de(admin)
    buscar = lambda q: c.get(reverse(LISTA), {"q": q}).content.decode()  # noqa: E731
    assert "Quispe Mamani" in buscar("1234") and "Torres" not in buscar("1234")  # por el principio del DNI
    assert "Torres, María" in buscar("maria@") and "Quispe" not in buscar("maria@")  # por el correo
    assert "Quispe Mamani, Rosa" in buscar("rosa quispe")  # nombre y apellido
    assert "Quispe Mamani, Rosa" in buscar("mamani rosa")  # apellido y nombre
    assert "No se encontró a nadie" in buscar("zzzz") and "Quitar filtros" in buscar("zzzz")


def test_filtrar_por_curso_y_turno(cliente_de, admin, docente, alumno, modulo, modulo_2):
    modulo.matricular(alumno)
    luis = alumno_de("40000001")
    modulo_2.matricular(luis)
    c = cliente_de(admin)
    manana = c.get(reverse(LISTA), {"especialidad": "Peluquería y Barbería", "turno": "mañana"}).content.decode()
    assert "Quispe Mamani" in manana and "Torres, María" in manana and "Paz, Luis" not in manana  # el docente dicta en ese curso
    noche = c.get(reverse(LISTA), {"turno": "noche"}).content.decode()
    assert "Paz, Luis" in noche and "Quispe Mamani" not in noche
    assert "Quispe Mamani" in c.get(reverse(LISTA), {"turno": "inventado"}).content.decode()  # un turno raro se ignora
    modulo.activo = False
    modulo.save()
    assert "Quispe Mamani" not in c.get(reverse(LISTA), {"turno": "mañana"}).content.decode()  # solo cuentan módulos activos


def test_paginar_la_lista(cliente_de, admin):
    for n in range(12):
        alumno_de(f"4000{n:04d}", f"Nombre{n}", f"Apellido{n:02d}")
    c = cliente_de(admin)
    primera = c.get(reverse(LISTA), {"por": 10}).content.decode()
    assert "Mostrando 1–10 de 13 personas" in primera and 'class="pag actual"' in primera and "Siguiente" in primera
    segunda = c.get(reverse(LISTA), {"por": 10, "pagina": 2}).content.decode()
    assert "Mostrando 11–13 de 13 personas" in segunda
    assert (
        "Mostrando 11–13" in c.get(reverse(LISTA), {"por": 10, "pagina": 99}).content.decode()
    )  # una página que no existe: la última
    assert "Mostrando 1–10" in c.get(reverse(LISTA), {"por": 10, "pagina": "x"}).content.decode()
    assert "Mostrando 1–13" in c.get(reverse(LISTA), {"por": 77}).content.decode()  # 25 por página


# ===================================================================== Crear


def test_pantalla_para_crear(cliente_de, admin, modulo, modulo_2):
    html = cliente_de(admin).get(reverse("cuentas:admin_nueva_persona") + "?rol=alumno").content.decode()
    assert "Nueva persona" in html and 'id="rol-alumno" value="alumno" checked' in html and "Contraseña inicial" in html
    assert "Inscribir en módulos" in html and "Peluquería y Barbería · Módulo 1" in html and "Prof. Torres" in html
    assert "Generar contraseña segura" in html and "@cetpro.com" in html
    assert 'name="forzar_cambio" value="1" checked' in html
    assert (
        'id="rol-docente" value="docente" checked'
        in cliente_de(admin).get(reverse("cuentas:admin_nueva_persona")).content.decode()
    )


def test_crear_docente_sin_contrasena_crea_una_al_azar(cliente_de, admin):
    c = cliente_de(admin)
    r = c.post(reverse(LISTA), datos(correo="profesortecnico", forzar_cambio=None))
    assert r["Location"] == reverse(LISTA)
    p = Usuario.objects.get(correo="profesortecnico@cetpro.com")  # se completa con el dominio
    assert (p.rol, p.nombres, p.apellidos, p.origen, p.is_active, p.is_staff) == (
        "docente",
        "Pedro",
        "Rojas Vega",
        Origen.ADMIN,
        True,
        False,
    )
    entregada = c.session["_clave_otro"]
    assert entregada["usuario"] == "profesortecnico@cetpro.com" and len(entregada["clave"]) >= 8 and entregada["forzar"] is True
    assert p.check_password(entregada["clave"]) and p.debe_cambiar_clave is True and p.activado is not None
    html = c.get(r["Location"]).content.decode()
    assert "Cuenta creada: Pedro Rojas Vega." in html and "Contraseña de Pedro Rojas Vega" in html and entregada["clave"] in html
    assert entregada["clave"] not in c.get(reverse(LISTA)).content.decode()  # se muestra una sola vez
    assert Registro.objects.filter(accion="cuenta", detalle__contains="creó la cuenta de Pedro Rojas Vega (Docente)").exists()


def test_crear_alumno_con_contrasena_y_modulos(cliente_de, admin, modulo, modulo_2):
    c = cliente_de(admin)
    r = c.post(
        reverse(LISTA),
        datos(
            rol="alumno",
            correo="",
            dni="45678912",
            nombres="Rosa",
            apellidos="Paredes",
            telefono="987 654 321",
            clave="mi-clave-1",
            fecha_nacimiento="1970-03-25",
            forzar_cambio=None,
        )
        | {"modulos[]": [modulo.pk, modulo_2.pk]},
    )
    p = Usuario.objects.get(dni="45678912")
    assert p.check_password("mi-clave-1") and p.debe_cambiar_clave is False and p.correo is None and p.telefono == "987 654 321"
    assert p.fecha_nacimiento.isoformat() == "1970-03-25" and set(p.matriculas.values_list("modulo", flat=True)) == {
        modulo.pk,
        modulo_2.pk,
    }
    assert c.session["_clave_otro"]["usuario"] == "45678912" and c.session["_clave_otro"]["forzar"] is False
    assert "Cuenta creada: Rosa Paredes · 2 módulos." in c.get(r["Location"]).content.decode()
    assert Registro.objects.filter(detalle__contains="y la inscribió en 2 módulos").exists()


def test_los_modulos_solo_se_inscriben_a_alumnos_y_activos(cliente_de, admin, modulo, modulo_2):
    modulo_2.activo = False
    modulo_2.save()
    c = cliente_de(admin)
    c.post(
        reverse(LISTA),
        datos(rol="alumno", correo="", dni="45678912", clave="mi-clave-1") | {"modulos[]": [modulo.pk, modulo_2.pk]},
    )
    assert list(Usuario.objects.get(dni="45678912").matriculas.values_list("modulo", flat=True)) == [modulo.pk]
    c.post(reverse(LISTA), datos(rol="docente", correo="otro@cetpro.com", clave="mi-clave-1") | {"modulos[]": [modulo.pk]})
    assert not Matricula.objects.filter(alumno__correo="otro@cetpro.com").exists()


@pytest.mark.parametrize(
    ("cambio", "mensaje"),
    [
        ({"correo": "", "dni": ""}, "Escribe el correo (docentes) o el DNI (alumnos) para que pueda entrar."),
        ({"correo": "", "dni": "1234567"}, "El DNI debe tener 8 números."),
        ({"nombres": " "}, "Escribe los nombres y apellidos."),
        ({"apellidos": ""}, "Escribe los nombres y apellidos."),
        ({"correo": "no es correo@x"}, "El correo no es válido."),
        ({"clave": "123"}, "La contraseña debe tener al menos 6 caracteres."),
    ],
)
def test_datos_incorrectos_al_crear(cliente_de, admin, cambio, mensaje):
    c = cliente_de(admin)
    r = c.post(reverse(LISTA), datos(**cambio))
    assert r["Location"] == reverse("cuentas:admin_nueva_persona")
    assert mensaje in c.get(r["Location"]).content.decode()
    assert not Usuario.objects.filter(nombres="Pedro").exists()


def test_no_se_repiten_ni_el_correo_ni_el_dni(cliente_de, admin, docente, alumno):
    c = cliente_de(admin)
    for cambio in ({"correo": "maria@cetpro.com"}, {"correo": "MARIA@Cetpro.com"}, {"correo": "", "dni": "12345678"}):
        r = c.post(reverse(LISTA), datos(**cambio))
        assert "Ya existe una persona con ese correo o DNI." in c.get(r["Location"]).content.decode()
    assert Usuario.objects.count() == 3


def test_al_volver_con_error_conserva_lo_escrito(cliente_de, admin, modulo):
    c = cliente_de(admin)
    r = c.post(
        reverse(LISTA),
        datos(rol="alumno", correo="", nombres="Rosa", apellidos="", dni="45678912", telefono="987654321")
        | {"modulos[]": [modulo.pk]},
    )
    html = c.get(r["Location"]).content.decode()
    assert (
        'value="Rosa"' in html
        and 'value="45678912"' in html
        and 'value="987654321"' in html
        and 'id="rol-alumno" value="alumno" checked' in html
    )
    assert f'value="{modulo.pk}" checked' in html


# ===================================================================== Editar


def test_pantalla_para_editar(cliente_de, admin, docente, alumno, modulo):
    modulo.matricular(alumno)
    c = cliente_de(admin)
    html = c.get(reverse("cuentas:admin_editar_persona", args=[alumno.pk])).content.decode()
    assert (
        "Editar persona" in html
        and 'value="Rosa"' in html
        and 'value="12345678"' in html
        and "Está en" in html
        and "Peluquería – M1" in html
    )
    assert "Dar contraseña nueva" in html and "Desactivar cuenta" in html and "Eliminar cuenta…" in html
    assert "Sus módulos" in c.get(reverse("cuentas:admin_editar_persona", args=[docente.pk])).content.decode()
    assert "Contraseña inicial" not in html and "Inscribir en módulos" not in html
    assert c.get(reverse("cuentas:admin_editar_persona", args=[99999])).status_code == 404


def test_editar_a_un_alumno_pendiente_lo_dice(cliente_de, admin):
    p = Usuario.objects.crear_alumno("40000003", "Pepe", "Soto")
    html = cliente_de(admin).get(reverse("cuentas:admin_editar_persona", args=[p.pk])).content.decode()
    assert "Aún no creó su contraseña" in html and "en «Crear mi cuenta» con su DNI" in html


def test_guardar_cambios(cliente_de, admin, alumno):
    c = cliente_de(admin)
    r = c.post(
        reverse("cuentas:admin_actualizar_persona", args=[alumno.pk]),
        datos(
            rol="alumno",
            correo="rosa",
            dni="12345678",
            nombres="Rosa María",
            apellidos="Quispe",
            telefono="987654321",
            fecha_nacimiento="1980-01-02",
        ),
    )
    assert r["Location"] == reverse(LISTA) and "Cambios guardados." in c.get(r["Location"]).content.decode()
    alumno.refresh_from_db()
    assert (alumno.nombres, alumno.apellidos, alumno.correo, alumno.telefono) == (
        "Rosa María",
        "Quispe",
        "rosa@cetpro.com",
        "987654321",
    )
    assert alumno.fecha_nacimiento.isoformat() == "1980-01-02"
    assert Registro.objects.filter(detalle__contains="editó los datos de Rosa Quispe Mamani").exists()
    # sin fecha escrita, la que había se conserva
    c.post(
        reverse("cuentas:admin_actualizar_persona", args=[alumno.pk]),
        datos(rol="alumno", correo="rosa", dni="12345678", nombres="Rosa", apellidos="Quispe"),
    )
    alumno.refresh_from_db()
    assert alumno.fecha_nacimiento.isoformat() == "1980-01-02"


def test_cambiar_el_rol(cliente_de, admin, alumno):
    cliente_de(admin).post(
        reverse("cuentas:admin_actualizar_persona", args=[alumno.pk]),
        datos(rol="docente", correo="rosa@cetpro.com", dni="12345678", nombres="Rosa", apellidos="Quispe"),
    )
    alumno.refresh_from_db()
    assert alumno.rol == Rol.DOCENTE


def test_nadie_se_quita_a_si_mismo_el_rol_de_administrador(cliente_de, admin):
    cliente_de(admin).post(
        reverse("cuentas:admin_actualizar_persona", args=[admin.pk]),
        datos(rol="alumno", correo="admin@cetpro.com", nombres="Ana", apellidos="Directora"),
    )
    admin.refresh_from_db()
    assert admin.rol == Rol.ADMIN


def test_editar_no_permite_repetir_datos_de_otra_persona(cliente_de, admin, docente, alumno):
    c = cliente_de(admin)
    url = reverse("cuentas:admin_actualizar_persona", args=[alumno.pk])
    r = c.post(url, datos(rol="alumno", correo="maria@cetpro.com", dni="12345678"))
    assert r["Location"] == reverse("cuentas:admin_editar_persona", args=[alumno.pk])
    assert "Ya existe otra persona con ese correo o DNI." in c.get(r["Location"]).content.decode()
    assert c.post(url, datos(rol="alumno", correo="", dni="12345678")).status_code == 302  # su propio DNI sí
    assert c.post(reverse("cuentas:admin_actualizar_persona", args=[99999]), datos()).status_code == 404


def test_solo_el_administrador_crea_o_edita(cliente_de, docente, alumno):
    for quien in (docente, alumno):
        c = cliente_de(quien)
        assert c.get(reverse("cuentas:admin_nueva_persona")).status_code == 403
        assert c.post(reverse(LISTA), datos()).status_code == 403
        assert c.get(reverse("cuentas:admin_editar_persona", args=[alumno.pk])).status_code == 403
        assert c.post(reverse("cuentas:admin_actualizar_persona", args=[alumno.pk]), datos()).status_code == 403
        assert c.post(reverse("cuentas:admin_clave_persona", args=[alumno.pk]), {}).status_code == 403
        assert c.post(reverse("cuentas:admin_estado_persona", args=[alumno.pk]), {}).status_code == 403
        assert c.post(reverse("cuentas:admin_lote"), {"ids[]": [alumno.pk], "accion": "desactivar"}).status_code == 403
        assert c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [alumno.pk], "confirmado": "1"}).status_code == 403
    assert Usuario.objects.filter(pk=alumno.pk, is_active=True).exists()


# ===================================================================== Contraseñas y estado


def test_dar_contrasena_nueva_propia(cliente_de, admin, alumno):
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_clave_persona", args=[alumno.pk]), {"clave": "nueva-clave-9", "forzar_cambio": "1"})
    assert r["Location"] == reverse("cuentas:admin_editar_persona", args=[alumno.pk])
    alumno.refresh_from_db()
    assert alumno.check_password("nueva-clave-9") and not alumno.check_password(CLAVE) and alumno.debe_cambiar_clave
    assert c.session["_clave_otro"] == {
        "nombre": "Rosa Quispe Mamani",
        "usuario": "12345678",
        "clave": "nueva-clave-9",
        "telefono": "",
        "forzar": True,
    }
    html = c.get(r["Location"]).content.decode()
    assert "Contraseña de Rosa Quispe Mamani" in html and "nueva-clave-9" in html and "Enviar por WhatsApp" in html
    assert "nueva-clave-9" not in c.get(r["Location"]).content.decode()
    assert Registro.objects.filter(accion="clave", detalle__contains="cambió la contraseña de Rosa").exists()
    assert "nueva-clave-9" not in "".join(Registro.objects.values_list("detalle", flat=True))  # nunca se guarda


def test_contrasena_propia_sin_obligar_el_cambio(cliente_de, admin, alumno):
    cliente_de(admin).post(reverse("cuentas:admin_clave_persona", args=[alumno.pk]), {"clave": "nueva-clave-9"})
    alumno.refresh_from_db()
    assert alumno.debe_cambiar_clave is False


def test_contrasena_vacia_crea_una_al_azar_y_siempre_se_cambia(cliente_de, admin, alumno):
    c = cliente_de(admin)
    c.post(reverse("cuentas:admin_clave_persona", args=[alumno.pk]), {"clave": ""})
    alumno.refresh_from_db()
    assert (
        alumno.check_password(c.session["_clave_otro"]["clave"])
        and alumno.debe_cambiar_clave
        and len(c.session["_clave_otro"]["clave"]) >= 8
    )


def test_contrasena_muy_corta(cliente_de, admin, alumno):
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_clave_persona", args=[alumno.pk]), {"clave": "123"})
    assert "La contraseña debe tener al menos 6 caracteres." in c.get(r["Location"]).content.decode()
    alumno.refresh_from_db()
    assert alumno.check_password(CLAVE)


def test_dar_contrasena_a_un_alumno_pendiente_lo_activa(cliente_de, admin):
    p = Usuario.objects.crear_alumno("40000003", "Pepe", "Soto")
    assert p.pendiente and p.activado is None
    cliente_de(admin).post(reverse("cuentas:admin_clave_persona", args=[p.pk]), {"clave": "clave-nueva"})
    p.refresh_from_db()
    assert not p.pendiente and p.activado is not None and p.check_password("clave-nueva")


def test_resetear_desde_la_lista_vuelve_a_la_lista_con_los_filtros(cliente_de, admin, alumno):
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_clave_persona", args=[alumno.pk]), {"desde": "lista", "volver": "?rol=alumno&por=10"})
    assert r["Location"] == reverse(LISTA) + "?rol=alumno&por=10"
    alumno.refresh_from_db()
    assert alumno.debe_cambiar_clave  # desde la lista siempre la cambia
    r = c.post(reverse("cuentas:admin_clave_persona", args=[alumno.pk]), {"desde": "lista", "volver": "https://malo.com"})
    assert r["Location"] == reverse(LISTA)  # un «volver» raro se ignora


def test_activar_y_desactivar_una_cuenta(cliente_de, admin, alumno):
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_estado_persona", args=[alumno.pk]), {})
    assert (
        r["Location"] == reverse("cuentas:admin_editar_persona", args=[alumno.pk])
        and "Estado actualizado." in c.get(r["Location"]).content.decode()
    )
    alumno.refresh_from_db()
    assert alumno.is_active is False
    assert "Activar cuenta" in c.get(r["Location"]).content.decode()
    # una cuenta desactivada ya no entra
    assert Client().post(reverse("cuentas:login"), {"usuario": "12345678", "clave": CLAVE, "tipo": "alumno"})[
        "Location"
    ] != reverse("nucleo:inicio")
    c.post(reverse("cuentas:admin_estado_persona", args=[alumno.pk]), {"desde": "lista", "volver": "?rol=inactivos"})
    alumno.refresh_from_db()
    assert alumno.is_active is True
    assert (
        Registro.objects.filter(detalle__contains="desactivó la cuenta de Rosa").exists()
        and Registro.objects.filter(detalle__contains="activó la cuenta de Rosa").exists()
    )


def test_nadie_desactiva_su_propia_cuenta(cliente_de, admin):
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_estado_persona", args=[admin.pk]), {})
    assert "No puedes desactivar tu propia cuenta." in c.get(r["Location"]).content.decode()
    admin.refresh_from_db()
    assert admin.is_active
    assert c.post(reverse("cuentas:admin_estado_persona", args=[99999]), {}).status_code == 404


# ===================================================================== Acciones en lote


def test_lote_dar_contrasena_nueva(cliente_de, admin, docente, alumno):
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_lote"), {"accion": "clave", "ids[]": [alumno.pk, docente.pk, admin.pk]})
    assert r["Location"] == reverse("cuentas:admin_claves")  # a uno mismo no se le cambia
    html = c.get(r["Location"]).content.decode()
    assert (
        "2 contraseñas nuevas creadas" in html
        and "Quispe Mamani" in html
        and "Torres" in html
        and "12345678" in html
        and "maria@cetpro.com" in html
    )
    assert "https://wa.me/" in html
    alumno.refresh_from_db()
    assert not alumno.check_password(CLAVE) and alumno.debe_cambiar_clave
    admin.refresh_from_db()
    assert admin.check_password(CLAVE)
    assert c.get(reverse("cuentas:admin_claves"))["Location"] == reverse(LISTA)  # una sola vez
    assert Registro.objects.filter(accion="clave", detalle__contains="dio contraseña nueva a 2 personas").exists()


def test_lote_activar_y_desactivar(cliente_de, admin, docente, alumno):
    c = cliente_de(admin)
    r = c.post(
        reverse("cuentas:admin_lote"),
        {"accion": "desactivar", "ids[]": [alumno.pk, docente.pk, admin.pk], "volver": "?rol=alumno"},
    )
    assert r["Location"] == reverse(LISTA) + "?rol=alumno"
    assert "2 cuentas desactivadas." in c.get(r["Location"]).content.decode()
    assert Usuario.objects.filter(is_active=False).count() == 2 and admin.is_active
    r = c.post(reverse("cuentas:admin_lote"), {"accion": "activar", "ids[]": [alumno.pk]})
    assert "1 cuenta activada." in c.get(r["Location"]).content.decode()
    assert Registro.objects.filter(detalle__contains="desactivó 2 cuentas").exists()


def test_lote_sin_marcar_o_sin_accion(cliente_de, admin, alumno):
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_lote"), {"accion": "activar"})
    assert "Marca primero a las personas a las que quieres aplicar la acción." in c.get(r["Location"]).content.decode()
    r = c.post(reverse("cuentas:admin_lote"), {"ids[]": [alumno.pk], "accion": "borrar-todo"})
    assert "Elige qué quieres hacer con las personas marcadas." in c.get(r["Location"]).content.decode()
    r = c.post(reverse("cuentas:admin_lote"), {"ids[]": [alumno.pk], "accion": ""})
    assert "Elige qué quieres hacer" in c.get(r["Location"]).content.decode()


# ===================================================================== Eliminar de verdad


def trabajar(alumno, modulo, docente, clase):
    """Le da al alumno de todo: trabajo con archivo, asistencia, test, aviso, pregunta, mensajes."""
    modulo.matricular(alumno)
    ruta, nombre = archivos.guardar(muestras.png("trabajo.png"))
    tarea = Tarea.objects.create(clase=clase, titulo="Foto", fecha_limite=timezone.now() + timezone.timedelta(days=3))
    Entrega.objects.create(tarea=tarea, alumno=alumno, archivo_ruta=ruta, archivo_nombre=nombre)
    Asistencia.objects.create(
        sesion=SesionAsistencia.objects.create(modulo=modulo, fecha=timezone.localdate()), alumno=alumno, estado="presente"
    )
    f = nuevo_formulario(clase)
    pregunta(f, "abierta", "x", puntos=1)
    Intento.objects.create(formulario=f, alumno=alumno, fin=timezone.now())
    PreguntaClase.objects.create(clase=clase, autor=alumno, texto="¿Cómo?")
    cv = Conversacion.obtener_o_crear(modulo, docente, alumno)
    cv.enviar(alumno, "Hola profe")
    cv.enviar(docente, "Hola")
    return Path(settings.MEDIA_ROOT) / ruta


def test_eliminar_primero_muestra_que_se_perdera(cliente_de, admin, docente, alumno, modulo, clase):
    archivo = trabajar(alumno, modulo, docente, clase)
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [alumno.pk], "volver": "?rol=alumno"})
    html = r.content.decode()
    assert (
        r.status_code == 200
        and "Eliminar cuentas" in html
        and "Vas a eliminar 1 cuenta." in html
        and "Esto no se puede deshacer." in html
    )
    assert "Rosa Quispe Mamani" in html and "su inscripción en 1 módulo" in html and "1 trabajo entregado" in html
    assert (
        "1 registro de asistencia" in html and "1 test rendido" in html and "1 pregunta de clase" in html and "1 mensaje" in html
    )
    assert 'name="entiendo"' in html and "Sí, eliminar esta cuenta" in html and 'name="volver" value="?rol=alumno"' in html
    assert Usuario.objects.filter(pk=alumno.pk).exists() and archivo.is_file()  # todavía no se borró nada


def test_eliminar_pide_marcar_entiendo_si_hay_datos(cliente_de, admin, docente, alumno, modulo, clase):
    trabajar(alumno, modulo, docente, clase)
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [alumno.pk], "confirmado": "1"})
    assert r.status_code == 200 and "Marca la casilla «Entiendo» para poder eliminar." in r.content.decode()
    assert Usuario.objects.filter(pk=alumno.pk).exists()


def test_eliminar_de_verdad_con_todo_lo_que_hizo(
    cliente_de, admin, docente, alumno, modulo, clase, django_capture_on_commit_callbacks
):
    archivo = trabajar(alumno, modulo, docente, clase)
    c = cliente_de(admin)
    with django_capture_on_commit_callbacks(execute=True):
        r = c.post(
            reverse("cuentas:admin_eliminar"), {"ids[]": [alumno.pk], "confirmado": "1", "entiendo": "1", "volver": "?rol=alumno"}
        )
    assert r["Location"] == reverse(LISTA) + "?rol=alumno"
    assert "1 cuenta eliminada." in c.get(r["Location"]).content.decode()
    assert not Usuario.objects.filter(pk=alumno.pk).exists() and not Matricula.objects.exists()
    assert (
        not Entrega.objects.exists()
        and not Asistencia.objects.exists()
        and not Intento.objects.exists()
        and not PreguntaClase.objects.exists()
    )
    assert not Conversacion.objects.exists() and not Mensaje.objects.exists()
    assert not archivo.exists()  # el archivo subido también se borra
    assert (
        Usuario.objects.filter(pk=docente.pk).exists() and Tarea.objects.exists() and SesionAsistencia.objects.exists()
    )  # lo del docente queda
    registro = Registro.objects.filter(
        accion="cuenta", detalle__contains="eliminó la cuenta de Rosa Quispe Mamani (Alumno)"
    ).get()
    assert (
        "Se borró también: 1 trabajo entregado, 1 registro de asistencia, 1 test rendido, 1 pregunta de clase, 1 mensaje."
        in registro.detalle
    )
    assert registro.usuario == admin


def test_eliminar_a_un_alumno_sin_datos_no_pide_entiendo(cliente_de, admin, alumno, modulo):
    modulo.matricular(alumno)
    c = cliente_de(admin)
    html = c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [alumno.pk]}).content.decode()
    assert 'name="entiendo"' not in html and "su inscripción en 1 módulo" in html
    c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [alumno.pk], "confirmado": "1"})
    assert not Usuario.objects.filter(pk=alumno.pk).exists()


def test_eliminar_a_un_docente_con_avisos(cliente_de, admin, modulo, docente):
    Aviso.crear(modulo, docente, "Recuerden traer su peine")
    otro = Usuario.objects.create_user(
        correo="otro@cetpro.com", nombres="Otro", apellidos="Docente", password=CLAVE, rol=Rol.DOCENTE
    )
    Aviso.crear(modulo, otro, "Aviso del otro")
    c = cliente_de(admin)
    html = c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [otro.pk]}).content.decode()
    assert "1 aviso publicado" in html and 'name="entiendo"' in html
    c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [otro.pk], "confirmado": "1", "entiendo": "1"})
    assert not Usuario.objects.filter(pk=otro.pk).exists() and Aviso.objects.count() == 1


def test_un_docente_con_modulos_no_se_elimina(cliente_de, admin, docente, modulo, modulo_2):
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [docente.pk]})
    html = r.content.decode()
    assert (
        "No se pueden eliminar todavía" in html
        and "Tiene a su cargo 2 módulos: cámbiales el docente o elimínalos primero." in html
    )
    assert "Peluquería – M1" in html and "Panadería – M1" in html and "Sí, eliminar" not in html and "Volver a Personas" in html
    r = c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [docente.pk], "confirmado": "1", "entiendo": "1"})
    assert "No se eliminó ninguna cuenta. 1 no se pudo eliminar" in c.get(r["Location"]).content.decode()
    assert Usuario.objects.filter(pk=docente.pk).exists()
    # cuando el docente ya no tiene módulos, sí
    Modulo.objects.update(activo=False)
    nuevo = Usuario.objects.create_user(
        correo="nuevo@cetpro.com", nombres="Nuevo", apellidos="Docente", password=CLAVE, rol=Rol.DOCENTE
    )
    Modulo.objects.update(docente=nuevo)
    c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [docente.pk], "confirmado": "1"})
    assert not Usuario.objects.filter(pk=docente.pk).exists()


def test_nadie_elimina_su_propia_cuenta(cliente_de, admin):
    c = cliente_de(admin)
    html = c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [admin.pk]}).content.decode()
    assert "Es tu propia cuenta." in html and "Sí, eliminar" not in html
    c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [admin.pk], "confirmado": "1"})
    assert Usuario.objects.filter(pk=admin.pk).exists()


def test_eliminar_varias_a_la_vez_con_una_que_no_se_puede(cliente_de, admin, docente, alumno, modulo):
    otra = alumno_de("40000001")
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_lote"), {"accion": "eliminar", "ids[]": [alumno.pk, otra.pk, docente.pk, admin.pk]})
    html = r.content.decode()
    assert (
        r.status_code == 200
        and "Vas a eliminar 2 cuentas." in html
        and "No se pueden eliminar todavía" in html
        and "estas 2 cuentas" in html
    )
    r = c.post(reverse("cuentas:admin_eliminar"), {"ids[]": [alumno.pk, otra.pk, docente.pk, admin.pk], "confirmado": "1"})
    assert "2 cuentas eliminadas. 2 no se pudieron eliminar" in c.get(r["Location"]).content.decode()
    assert set(Usuario.objects.values_list("pk", flat=True)) == {docente.pk, admin.pk}


def test_eliminar_sin_marcar_o_con_personas_que_no_existen(cliente_de, admin):
    c = cliente_de(admin)
    r = c.post(reverse("cuentas:admin_eliminar"), {})
    assert "Marca primero a las personas que quieres eliminar." in c.get(r["Location"]).content.decode()
    r = c.post(reverse("cuentas:admin_eliminar"), {"ids[]": ["99999", "abc"]})
    assert "No se encontró a las personas que marcaste." in c.get(r["Location"]).content.decode()
    assert c.get(reverse("cuentas:admin_eliminar")).status_code == 405


def test_desde_la_ficha_se_puede_eliminar(cliente_de, admin, alumno):
    html = cliente_de(admin).get(reverse("cuentas:admin_editar_persona", args=[alumno.pk])).content.decode()
    assert f'name="ids[]" value="{alumno.pk}"' in html and reverse("cuentas:admin_eliminar") in html
