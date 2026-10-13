"""Cargar una lista de alumnos (Excel, CSV o pegada): crear cuentas pendientes, inscribirlos y dar contraseñas temporales."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.academico.models import Modulo
from apps.cuentas.importar_alumnos import fecha_flexible, numero_del_modulo, numeros_de_modulo
from apps.cuentas.models import Origen, Rol, Usuario
from apps.nucleo.models import Registro

from .conftest import CLAVE
from .test_importador import xlsx

pytestmark = pytest.mark.django_db

URL = "cuentas:admin_importar"


@pytest.fixture
def modulo_1(docente):
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
        nombre="Peluquería – M2",
        especialidad="Peluquería y Barbería",
        modulo="Módulo II",
        periodo="2026-II",
        turno="tarde",
        docente=docente,
    )


def cargar(c, lista="", marcados=(), con_clave=True, **extra):
    datos = {"lista": lista, "curso_id[]": [m.pk for m in marcados], **extra}
    if con_clave:
        datos["con_clave"] = "1"
    return c.post(reverse(URL), datos)


# ===================================================================== Pantalla


def test_pantalla_de_cargar_alumnos(cliente_de, admin, modulo_1, modulo_2):
    html = cliente_de(admin).get(reverse(URL)).content.decode()
    assert "Cargar alumnos" in html and "Cargar la lista" in html and "Peluquería y Barbería" in html
    assert (
        "Módulo 1 · «Peluquería – M1» · mañana · Prof. Torres" in html
        and "Módulo II · «Peluquería – M2» · tarde" in html
        and 'name="curso_id[]"' in html
    )
    assert 'name="con_clave" value="1" checked' in html and "Cómo debe ser la lista" in html and "no se guarda" in html


def test_sin_modulos(cliente_de, admin):
    assert "Todavía no hay módulos." in cliente_de(admin).get(reverse(URL)).content.decode()


def test_solo_el_administrador_carga_alumnos(cliente_de, docente, alumno):
    for quien in (docente, alumno):
        c = cliente_de(quien)
        assert c.get(reverse(URL)).status_code == 403
        assert c.post(reverse(URL), {"lista": "45678912\tRosa\tParedes"}).status_code == 403
    assert not Usuario.objects.filter(dni="45678912").exists()


# ===================================================================== Lista pegada


def test_cargar_una_lista_pegada(cliente_de, admin, modulo_1, modulo_2):
    c = cliente_de(admin)
    lista = "45678912\tROSA MARÍA\tparedes QUISPE\t987654321\n12345677;Luis;Paz Soto;;\n\n"
    r = cargar(c, lista, [modulo_1, modulo_2])
    assert r["Location"] == reverse(URL)
    rosa, luis = Usuario.objects.get(dni="45678912"), Usuario.objects.get(dni="12345677")
    assert (rosa.nombres, rosa.apellidos, rosa.telefono, rosa.rol, rosa.origen) == (
        "Rosa María",
        "Paredes Quispe",
        "987654321",
        Rol.ALUMNO,
        Origen.LISTA,
    )
    assert (luis.nombres, luis.apellidos, luis.telefono) == ("Luis", "Paz Soto", "")
    assert set(rosa.matriculas.values_list("modulo", flat=True)) == {modulo_1.pk, modulo_2.pk} and luis.matriculas.count() == 2
    html = c.get(r["Location"]).content.decode()
    assert (
        "Lista cargada" in html and "2 alumnos nuevos · 4 inscripciones en módulos" in html and "2 contraseñas temporales" in html
    )
    assert "Ver contraseñas y enviar por WhatsApp" in html
    assert "Lista cargada" not in c.get(reverse(URL)).content.decode()  # el resultado se muestra una sola vez
    assert Registro.objects.filter(
        accion="cuenta", detalle__contains="cargó una lista: 2 alumnos nuevos, 4 inscripciones y 2 contraseñas temporales"
    ).exists()


def test_las_contrasenas_temporales_se_muestran_una_vez(cliente_de, admin, modulo_1):
    c = cliente_de(admin)
    cargar(c, "45678912\tRosa\tParedes\t987654321", [modulo_1])
    rosa = Usuario.objects.get(dni="45678912")
    assert not rosa.pendiente and rosa.debe_cambiar_clave and rosa.activado is not None
    r = c.get(reverse("cuentas:admin_claves"))
    html = r.content.decode()
    assert "1 contraseña nueva creada" in html and "Rosa Paredes" in html and "45678912" in html and "wa.me/51987654321" in html
    assert "_claves_lote" not in c.session  # ya se consumió
    assert c.get(reverse("cuentas:admin_claves"))["Location"] == reverse("cuentas:admin_personas")


def test_sin_contrasena_temporal_quedan_pendientes(cliente_de, admin, modulo_1):
    c = cliente_de(admin)
    r = cargar(c, "45678912\tRosa\tParedes", [modulo_1], con_clave=False)
    rosa = Usuario.objects.get(dni="45678912")
    assert rosa.pendiente and rosa.activado is None and rosa.matriculas.count() == 1
    html = c.get(r["Location"]).content.decode()
    assert "Los alumnos nuevos entran a «Crear mi cuenta»" in html and "Ver contraseñas" not in html
    assert "_claves_lote" not in c.session


def test_un_alumno_que_ya_existe_solo_se_inscribe(cliente_de, admin, alumno, modulo_1):
    c = cliente_de(admin)
    r = cargar(c, "12345678\tOtro nombre\tOtro apellido\t999888777", [modulo_1])
    alumno.refresh_from_db()
    assert alumno.nombres == "Rosa" and alumno.telefono == "" and alumno.check_password(CLAVE)  # no se toca lo que ya tiene
    assert alumno.matriculas.count() == 1 and Usuario.objects.filter(rol=Rol.ALUMNO).count() == 1
    assert "0 alumnos nuevos · 1 inscripción en módulo" in c.get(r["Location"]).content.decode()
    cargar(c, "12345678\tOtro\tOtro", [modulo_1])  # otra vez: no se duplica la inscripción
    assert alumno.matriculas.count() == 1


def test_alumno_pendiente_que_ya_existe_recibe_su_contrasena(cliente_de, admin, modulo_1):
    p = Usuario.objects.crear_alumno("45678912", "Rosa", "Paredes", telefono="987654321")
    c = cliente_de(admin)
    cargar(c, "45678912\tRosa\tParedes", [modulo_1])
    p.refresh_from_db()
    assert not p.pendiente and p.debe_cambiar_clave
    assert c.session["_claves_lote"][0]["telefono"] == "987654321"  # usa el celular que ya tenía


def test_nombres_y_apellidos_en_minusculas_pasan_a_titulo(cliente_de, admin):
    cargar(cliente_de(admin), "45678912\tmaría de los ángeles\tDE LA CRUZ\t", [])
    p = Usuario.objects.get(dni="45678912")
    assert (p.nombres, p.apellidos) == ("María De Los Ángeles", "De La Cruz") and p.matriculas.count() == 0


def test_el_dni_de_7_digitos_recupera_su_cero(cliente_de, admin):
    cargar(cliente_de(admin), "5678912\tRosa\tParedes", [])
    assert Usuario.objects.filter(dni="05678912").exists()


def test_celular_valido_solo_con_9_digitos(cliente_de, admin):
    cargar(cliente_de(admin), "11111111\tUno\tUno\t987-654-321\n22222222\tDos\tDos\t12345\n", [])
    assert Usuario.objects.get(dni="11111111").telefono == "987654321" and Usuario.objects.get(dni="22222222").telefono == ""


def test_errores_en_algunas_filas(cliente_de, admin, docente, modulo_1):
    c = cliente_de(admin)
    lista = "123\tCorto\tApellido\n45678912\tRosa\tParedes\n77777777\t\t\n99999999\tSin\t\nmaria@cetpro.com\tMaría\tTorres\n"
    r = cargar(c, lista, [modulo_1])
    html = c.get(r["Location"]).content.decode()
    assert "1 alumno nuevo" in html and "Estas filas no se cargaron:" in html
    assert "Fila 1: el DNI debe tener 8 números." in html and "Fila 3: falta el nombre o el apellido (DNI 77777777)." in html
    assert "Fila 4: falta el nombre o el apellido (DNI 99999999)." in html and "Fila 5: el DNI debe tener 8 números." in html
    assert Usuario.objects.filter(rol=Rol.ALUMNO).count() == 1


def test_el_dni_de_un_docente_no_se_toca(cliente_de, admin, modulo_1):
    from apps.cuentas.models import Usuario as U

    U.objects.create_user(
        correo="p@cetpro.com", dni="55555555", nombres="Pedro", apellidos="Rojas", password=CLAVE, rol=Rol.DOCENTE
    )
    c = cliente_de(admin)
    r = cargar(c, "55555555\tPedro\tRojas", [modulo_1])
    assert "Fila 1: el DNI 55555555 es de un docente." in c.get(r["Location"]).content.decode()
    assert not U.objects.get(dni="55555555").matriculas.exists()


def test_sin_filas_o_vacia(cliente_de, admin):
    c = cliente_de(admin)
    for lista in ("", "   \n \n"):
        r = cargar(c, lista, [])
        assert "No se encontró ninguna fila. Sube un Excel o pega la lista." in c.get(r["Location"]).content.decode()


def test_al_volver_con_error_se_conserva_la_lista(cliente_de, admin):
    c = cliente_de(admin)
    r = c.post(reverse(URL), {"lista": ""})
    assert r["Location"] == reverse(URL)
    r = c.post(reverse(URL), {"archivo": SimpleUploadedFile("x.pdf", b"x")})
    assert "Sube un archivo de Excel (.xlsx) o CSV." in c.get(r["Location"]).content.decode()


# ===================================================================== Títulos de columna y módulos


EXCEL_DE_MATRICULA = (
    "Marca temporal;Apellido paterno;Apellido materno;Nombres;DNI;Edad;Dirección;Estado civil;Teléfono;Fecha de nacimiento;Módulo\n"
    "10/10/2026;Paredes;Quispe;Rosa María;45678912;56;Av. Los Pinos 123;Casada;987654321;25/03/1970;1 y 2\n"
    "10/10/2026;Paz;Soto;Luis;12345677;30;Jr. Lima 45;Soltero;;1999-07-01;2\n"
    "10/10/2026;Vega;Ríos;Ana;11112222;41;Calle 5;Soltera;912345678;45000;Módulo I\n"
)


def test_el_excel_de_la_matricula_tal_cual(cliente_de, admin, modulo_1, modulo_2):
    c = cliente_de(admin)
    r = c.post(
        reverse(URL),
        {
            "archivo": SimpleUploadedFile("matricula.csv", EXCEL_DE_MATRICULA.encode()),
            "curso_id[]": [modulo_1.pk, modulo_2.pk],
            "con_clave": "1",
        },
    )
    rosa, luis, ana = (Usuario.objects.get(dni=d) for d in ("45678912", "12345677", "11112222"))
    assert (rosa.nombres, rosa.apellidos, rosa.telefono, rosa.fecha_nacimiento) == (
        "Rosa María",
        "Paredes Quispe",
        "987654321",
        date(1970, 3, 25),
    )
    assert set(rosa.matriculas.values_list("modulo", flat=True)) == {modulo_1.pk, modulo_2.pk}  # «1 y 2»
    assert list(luis.matriculas.values_list("modulo", flat=True)) == [modulo_2.pk] and luis.fecha_nacimiento == date(
        1999, 7, 1
    )  # «2»
    assert list(ana.matriculas.values_list("modulo", flat=True)) == [modulo_1.pk] and ana.fecha_nacimiento == date(
        2023, 3, 15
    )  # «Módulo I» y fecha de Excel
    assert not hasattr(rosa, "direccion") and "Casada" not in str(rosa.__dict__)  # lo demás no se guarda
    assert "3 alumnos nuevos · 4 inscripciones en módulos" in c.get(r["Location"]).content.decode()


def test_excel_xlsx(cliente_de, admin, modulo_1):
    filas = [
        ["DNI", "Nombres", "Apellidos", "Celular"],
        ["45678912", "Rosa", "Paredes", "987654321"],
        ["12345677", "Luis", "Paz", None],
    ]
    archivo = SimpleUploadedFile("lista.xlsx", xlsx(filas).getvalue())
    c = cliente_de(admin)
    r = c.post(reverse(URL), {"archivo": archivo, "curso_id[]": [modulo_1.pk]})
    assert Usuario.objects.filter(dni__in=["45678912", "12345677"]).count() == 2
    assert "2 alumnos nuevos · 2 inscripciones en módulos" in c.get(r["Location"]).content.decode()


def test_lista_sin_titulos_va_por_posicion(cliente_de, admin):
    cargar(cliente_de(admin), "45678912,Rosa,Paredes,987654321,25/03/1970", [])
    p = Usuario.objects.get(dni="45678912")
    assert p.fecha_nacimiento == date(1970, 3, 25) and p.telefono == "987654321"


def test_una_lista_grande_no_se_corta_en_100(cliente_de, admin):
    filas = [["DNI", "Nombres", "Apellidos"]] + [[f"{30000000 + n}", f"Alumno{n}", "Prueba"] for n in range(250)]
    r = cliente_de(admin).post(reverse(URL), {"archivo": SimpleUploadedFile("lista.xlsx", xlsx(filas).getvalue())})
    assert r.status_code == 302 and Usuario.objects.filter(rol=Rol.ALUMNO).count() == 250


def test_el_modulo_por_codigo(cliente_de, admin, modulo_1, modulo_2):
    c = cliente_de(admin)
    lista = f"DNI;Nombres;Apellidos;Módulo\n45678912;Rosa;Paredes;{modulo_2.codigo_fmt}\n12345677;Luis;Paz;{modulo_1.codigo.lower()} y {modulo_2.codigo}\n"
    cargar(c, lista, [])
    assert list(Usuario.objects.get(dni="45678912").matriculas.values_list("modulo", flat=True)) == [modulo_2.pk]
    assert set(Usuario.objects.get(dni="12345677").matriculas.values_list("modulo", flat=True)) == {modulo_1.pk, modulo_2.pk}


def test_modulos_que_no_se_pueden_resolver(cliente_de, admin, modulo_1):
    c = cliente_de(admin)
    lista = "DNI;Nombres;Apellidos;Módulo\n11111111;Uno;Uno;ZZZ-9999\n22222222;Dos;Dos;tercero\n33333333;Tres;Tres;2\n44444444;Cuatro;Cuatro;1\n"
    r = cargar(c, lista, [modulo_1])
    html = c.get(r["Location"]).content.decode()
    assert "Fila 1: no existe el módulo con código «ZZZ-9999»." in html
    assert "Fila 2: no entendí el módulo «tercero» (escribe 1, 2 o «1 y 2»)." in html
    assert "Fila 3: marca arriba el módulo «2» para poder inscribirlo." in html
    assert Usuario.objects.filter(rol=Rol.ALUMNO).count() == 4 - 3  # solo se cargó la fila 4
    assert list(Usuario.objects.get(dni="44444444").matriculas.values_list("modulo", flat=True)) == [modulo_1.pk]


def test_los_errores_se_limitan_a_50(cliente_de, admin):
    lista = "\n".join(f"{n}\tNombre\tApellido" for n in range(80))  # ninguna fila tiene un DNI de 8 números
    c = cliente_de(admin)
    r = cargar(c, lista, [])
    assert r.status_code == 302 and len(c.session["_importacion"]["errores"]) == 50
    assert "Fila 50:" in c.get(r["Location"]).content.decode() and "Fila 51:" not in c.get(reverse(URL)).content.decode()


# ===================================================================== Ayudas


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1", [1]),
        ("2", [2]),
        ("1 y 2", [1, 2]),
        ("Módulo II", [2]),
        ("módulo iii", [3]),
        ("IV", [4]),
        ("ambos", None),
        ("los dos", None),
        ("Todos", None),
        ("", False),
        ("tercero", False),
    ],
)
def test_numeros_de_modulo(texto, esperado):
    assert numeros_de_modulo(texto) == esperado


def test_numero_de_un_modulo_por_su_nombre():
    assert (
        numero_del_modulo("Módulo 2") == 2 and numero_del_modulo("Módulo II") == 2 and numero_del_modulo("Módulo 1 y 2") is None
    )
    assert numero_del_modulo("") is None


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("25/03/1970", date(1970, 3, 25)),
        ("1970-03-25", date(1970, 3, 25)),
        ("25-03-1970", date(1970, 3, 25)),
        ("25569", date(1970, 1, 1)),  # número de fecha de Excel
        ("45000", date(2023, 3, 15)),
        ("", None),
        ("31/02/2000", None),
        ("01/01/1800", None),
        ("pronto", None),
        ("12", None),
    ],
)
def test_fecha_flexible(texto, esperado):
    assert fecha_flexible(texto) == esperado
