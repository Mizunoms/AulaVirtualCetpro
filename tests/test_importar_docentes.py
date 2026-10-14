"""Cargar una lista de docentes (Excel, CSV o pegada): cuentas con contraseña temporal para enviar por WhatsApp."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.cuentas.importar_docentes import ENCABEZADO_MODELO, correo_para
from apps.cuentas.models import Origen, Rol, Usuario
from apps.nucleo.models import Registro

from .test_importador import xlsx

pytestmark = pytest.mark.django_db

URL = "cuentas:admin_importar_docentes"


def cargar(c, lista="", **extra):
    return c.post(reverse(URL), {"lista": lista, **extra})


def resultado(c, r):
    """La pantalla a la que vuelve después de cargar."""
    return c.get(r["Location"]).content.decode()


# ===================================================================== Pantalla


def test_pantalla_de_cargar_docentes_solo_la_ve_el_administrador(cliente_de, admin, docente, alumno):
    html = cliente_de(admin).get(reverse(URL)).content.decode()
    assert "Cargar la lista" in html and "Cargar docentes" in html and "Descargar modelo para Excel" in html
    assert "nombre.apellido@cetpro.com" in html  # el dominio sale de los ajustes del aula
    for persona in (docente, alumno):
        assert cliente_de(persona).get(reverse(URL)).status_code == 403
        assert cliente_de(persona).post(reverse(URL), {"lista": "Ana\tPaz"}).status_code == 403


def test_hay_un_boton_en_personas_para_cargar_la_lista_de_docentes(cliente_de, admin):
    html = cliente_de(admin).get(reverse("cuentas:admin_personas")).content.decode()
    assert "Cargar lista de docentes" in html and reverse(URL) in html and "Cargar lista de alumnos" in html


# ===================================================================== Cargar


def test_lista_pegada_crea_docentes_con_su_correo_y_contrasena_temporal(cliente_de, admin):
    c = cliente_de(admin)
    r = cargar(c, "Rosa Elena\tParedes Huamán\trosa.paredes@cetpro.com\t45678912\t987654321\nJorge\tSalazar Ríos\t\t\t")
    html = resultado(c, r)
    assert "2 docentes nuevos" in html and "2 contraseñas temporales" in html

    rosa = Usuario.objects.get(correo="rosa.paredes@cetpro.com")
    assert (rosa.rol, rosa.nombres, rosa.apellidos, rosa.dni, rosa.telefono) == (
        Rol.DOCENTE, "Rosa Elena", "Paredes Huamán", "45678912", "987654321"
    )  # fmt: skip
    assert rosa.origen == Origen.LISTA and rosa.debe_cambiar_clave and rosa.is_active and not rosa.pendiente
    jorge = Usuario.objects.get(nombres="Jorge")
    assert jorge.correo == "jorge.salazar@cetpro.com" and jorge.dni is None  # sin correo: el aula lo arma


def test_las_contrasenas_se_muestran_una_sola_vez_con_su_enlace_de_whatsapp(cliente_de, admin):
    c = cliente_de(admin)
    cargar(c, "Rosa\tParedes\trosa.paredes@cetpro.com\t\t987654321")
    html = c.get(reverse("cuentas:admin_claves")).content.decode()
    assert "rosa.paredes@cetpro.com" in html and "Rosa Paredes" in html and "wa.me/51987654321" in html
    assert "_claves_lote" not in c.session
    assert c.get(reverse("cuentas:admin_claves"))["Location"] == reverse("cuentas:admin_personas")


def test_el_docente_entra_con_la_contrasena_temporal_y_debe_cambiarla(cliente_de, admin, client):
    c = cliente_de(admin)
    cargar(c, "Rosa\tParedes\trosa.paredes@cetpro.com")
    clave = c.session["_claves_lote"][0]["clave"]
    r = client.post(reverse("cuentas:login"), {"usuario": "rosa.paredes@cetpro.com", "clave": clave, "tipo": "personal"})
    assert r.status_code == 302
    # Antes de usar el aula le pide elegir su propia contraseña
    assert client.get(reverse("nucleo:inicio"))["Location"] == reverse("cuentas:nueva_clave")


def test_ni_las_contrasenas_ni_los_datos_de_mas_quedan_en_el_registro(cliente_de, admin):
    c = cliente_de(admin)
    cargar(c, "Rosa\tParedes\trosa.paredes@cetpro.com\t45678912\t987654321")
    clave = c.session["_claves_lote"][0]["clave"]
    texto = " ".join(Registro.objects.values_list("detalle", flat=True))
    assert "cargó una lista de docentes: 1 docente nuevo" in texto
    assert clave not in texto and "45678912" not in texto and "987654321" not in texto


def test_con_titulos_en_cualquier_orden_y_apellidos_separados(cliente_de, admin):
    c = cliente_de(admin)
    lista = (
        "Celular;Apellido paterno;Apellido materno;Nombres;Correo electrónico\n987654321;PAREDES;HUAMÁN;ROSA ELENA;rosaparedes"
    )
    r = cargar(c, lista)
    assert "1 docente nuevo" in resultado(c, r)
    rosa = Usuario.objects.get(dni=None, nombres="Rosa Elena")
    assert rosa.apellidos == "Paredes Huamán"  # las mayúsculas del Excel se arreglan
    assert rosa.correo == "rosaparedes@cetpro.com"  # solo la parte de antes de la @: se completa con el dominio
    assert rosa.telefono == "987654321"


def test_celular_con_codigo_de_pais_y_dni_sin_cero_inicial(cliente_de, admin):
    c = cliente_de(admin)
    cargar(c, "Rosa\tParedes\t\t4567891\t+51 987 654 321")
    rosa = Usuario.objects.get(nombres="Rosa")
    assert rosa.dni == "04567891" and rosa.telefono == "987654321"


def test_dos_docentes_con_el_mismo_nombre_reciben_correos_distintos(cliente_de, admin):
    c = cliente_de(admin)
    cargar(c, "Rosa\tParedes\t\t11111111\nRosa\tParedes\t\t22222222")
    assert sorted(Usuario.objects.filter(rol=Rol.DOCENTE).values_list("correo", flat=True)) == [
        "rosa.paredes2@cetpro.com", "rosa.paredes@cetpro.com"
    ]  # fmt: skip
    assert correo_para("Rosa", "Paredes") == "rosa.paredes3@cetpro.com"


def test_correo_para_quita_tildes_y_usa_el_primer_nombre_y_apellido(db):
    assert correo_para("María José", "Núñez de la Torre") == "maria.nunez@cetpro.com"
    assert correo_para("Ñ", "Ñ") == "n.n@cetpro.com"


# ===================================================================== Repetidos y errores


def test_volver_a_cargar_la_misma_lista_no_duplica_ni_cambia_contrasenas(cliente_de, admin, client):
    c = cliente_de(admin)
    lista = "Rosa\tParedes\trosa.paredes@cetpro.com\t45678912\nJorge\tSalazar\t\t\t"
    cargar(c, lista)
    c.get(reverse("cuentas:admin_claves"))  # las contraseñas de la primera vez ya se vieron
    antes = {u.pk: u.password for u in Usuario.objects.filter(rol=Rol.DOCENTE)}
    r = cargar(c, lista)
    html = resultado(c, r)
    assert "0 docentes nuevos" in html and "2 ya estaban" in html and "No había docentes nuevos" in html
    assert Usuario.objects.filter(rol=Rol.DOCENTE).count() == 2
    assert {u.pk: u.password for u in Usuario.objects.filter(rol=Rol.DOCENTE)} == antes  # nadie se queda sin entrar
    assert "_claves_lote" not in c.session


def test_si_el_correo_o_el_dni_es_de_otra_persona_la_fila_no_se_carga(cliente_de, admin, alumno):
    c = cliente_de(admin)
    r = cargar(c, f"Ana\tTorres\t\t{alumno.dni}\nPedro\tRojas\t{admin.correo}")
    html = resultado(c, r)
    assert "ya pertenece a otra persona (alumno)" in html and "ya pertenece a otra persona (administrador)" in html
    assert "0 docentes nuevos" in html
    assert Usuario.objects.filter(rol=Rol.DOCENTE).count() == 0


def test_filas_con_problemas_se_cuentan_y_las_buenas_si_se_cargan(cliente_de, admin):
    c = cliente_de(admin)
    lista = "\n".join(
        [
            "Rosa\tParedes\trosa.paredes@cetpro.com",  # bien
            "\tParedes\tsin.nombre@cetpro.com",  # falta el nombre
            "Jorge\t\t\t",  # falta el apellido
            "Luis\tPaz\tcorreo mal escrito@@\t",  # correo no válido
            "Eva\tDíaz\t\t1234",  # DNI corto
            "\t\t\t",  # fila vacía: se ignora sin avisar
        ]
    )
    html = resultado(c, cargar(c, lista))
    assert "1 docente nuevo" in html and "Estas filas no se cargaron" in html
    assert "Fila 2: falta el nombre o el apellido." in html and "Fila 3: falta el nombre o el apellido." in html
    assert "Fila 4 (Luis Paz): el correo" in html and "Fila 5 (Eva Díaz): el DNI debe tener 8 números." in html
    assert "Fila 6" not in html
    assert Usuario.objects.filter(rol=Rol.DOCENTE).count() == 1


def test_sin_filas_o_con_un_archivo_que_no_sirve(cliente_de, admin):
    c = cliente_de(admin)
    assert "No se encontró ninguna fila" in resultado(c, cargar(c, ""))
    r = c.post(reverse(URL), {"archivo": SimpleUploadedFile("lista.pdf", b"x")})
    assert "Sube un archivo de Excel (.xlsx) o CSV." in resultado(c, r)


def test_con_titulos_pero_sin_la_columna_de_nombres_se_avisa_una_sola_vez(cliente_de, admin):
    c = cliente_de(admin)
    html = resultado(c, cargar(c, "Correo;DNI\nrosa@cetpro.com;45678912"))
    assert "No encuentro la columna «Nombres»" in html and Usuario.objects.filter(rol=Rol.DOCENTE).count() == 0
    html = resultado(c, cargar(c, "Nombres;Correo\nRosa;rosa@cetpro.com"))
    assert "No encuentro la columna «Apellidos»" in html


# ===================================================================== Excel y CSV


def test_excel_xlsx_con_titulos(cliente_de, admin):
    c = cliente_de(admin)
    filas = [
        ["Nombres", "Apellidos", "Correo", "DNI", "Celular"],
        ["Rosa Elena", "Paredes Huamán", "rosa.paredes@cetpro.com", 45678912, 987654321],  # Excel guarda los números como números
        ["Jorge", "Salazar Ríos", None, None, None],
    ]
    r = c.post(reverse(URL), {"archivo": SimpleUploadedFile("docentes.xlsx", xlsx(filas).getvalue())})
    assert "2 docentes nuevos" in resultado(c, r)
    assert Usuario.objects.get(correo="rosa.paredes@cetpro.com").dni == "45678912"


def test_csv_con_punto_y_coma_y_tildes(cliente_de, admin):
    c = cliente_de(admin)
    csv = "Nombres;Apellidos;Correo\r\nMaría;Núñez Quispe;maria@cetpro.com\r\n".encode(
        "cp1252"
    )  # como lo guarda Excel en español
    r = c.post(reverse(URL), {"archivo": SimpleUploadedFile("docentes.csv", csv)})
    assert "1 docente nuevo" in resultado(c, r)
    assert Usuario.objects.get(correo="maria@cetpro.com").nombre_completo == "María Núñez Quispe"


# ===================================================================== Modelo para Excel


def test_el_modelo_de_docentes_se_descarga_y_se_puede_volver_a_subir(cliente_de, admin):
    c = cliente_de(admin)
    r = c.get(reverse("cuentas:admin_modelo_docentes"))
    assert r.status_code == 200 and "attachment" in r["Content-Disposition"] and r["Content-Type"].startswith("text/csv")
    contenido = r.content.decode("utf-8")
    assert contenido.startswith("﻿") and contenido.strip().lstrip("﻿") == ";".join(ENCABEZADO_MODELO)
    # Con una fila llenada debajo de los títulos del modelo, se carga bien
    llena = SimpleUploadedFile("modelo.csv", r.content + b"Rosa;Paredes;;;987654321\r\n")
    assert "1 docente nuevo" in resultado(c, c.post(reverse(URL), {"archivo": llena}))


def test_el_modelo_de_alumnos_se_descarga_y_solo_lo_ve_el_administrador(cliente_de, admin, docente):
    r = cliente_de(admin).get(reverse("cuentas:admin_modelo_alumnos"))
    assert (
        r.status_code == 200
        and "Apellidos paterno;Apellidos materno;Nombres;DNI;Teléfono;Fecha de nacimiento;Módulo" in r.content.decode()
    )
    assert cliente_de(docente).get(reverse("cuentas:admin_modelo_alumnos")).status_code == 403
    assert cliente_de(docente).get(reverse("cuentas:admin_modelo_docentes")).status_code == 403


def test_el_modelo_de_alumnos_se_entiende_al_cargarlo(cliente_de, admin):
    c = cliente_de(admin)
    r = c.get(reverse("cuentas:admin_modelo_alumnos"))
    llena = SimpleUploadedFile("modelo.csv", r.content + "Paredes;Quispe;Rosa María;45678912;987654321;25/03/1970;\r\n".encode())
    html = resultado(c, c.post(reverse("cuentas:admin_importar"), {"archivo": llena, "con_clave": "1"}))
    assert "1 alumno nuevo" in html
    assert Usuario.objects.get(dni="45678912").fecha_nacimiento.year == 1970
