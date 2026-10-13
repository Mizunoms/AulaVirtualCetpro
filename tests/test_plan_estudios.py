"""Cargar el plan de estudios (Excel del Ministerio): leer el archivo, revisar lo que se encontró y crear o completar módulos."""

import io
import re
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.academico import plan_estudios
from apps.academico.models import Modulo, UnidadDidactica
from apps.cuentas.models import Rol, Usuario
from apps.nucleo import ajustes
from apps.nucleo.importador import ImportadorError
from apps.nucleo.models import Registro

from .conftest import CLAVE

pytestmark = pytest.mark.django_db

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def libro(hojas, compartidas=True):
    """Arma un .xlsx con varias hojas: {nombre de la hoja: {fila: {columna: valor}}}."""
    textos = []
    parte_hojas, rels, ids = {}, [], []
    for n, (nombre, filas) in enumerate(hojas.items(), start=1):
        filas_xml = []
        for fila in sorted(filas):
            celdas = []
            for col in sorted(filas[fila]):
                valor, ref = filas[fila][col], f"{LETRAS[col]}{fila}"
                if isinstance(valor, (int, float)):
                    celdas.append(f'<c r="{ref}"><v>{valor}</v></c>')
                elif compartidas:
                    textos.append(valor)
                    celdas.append(f'<c r="{ref}" t="s"><v>{len(textos) - 1}</v></c>')
                else:
                    celdas.append(f'<c r="{ref}" t="inlineStr"><is><t>{valor}</t></is></c>')
            filas_xml.append(f'<row r="{fila}">{"".join(celdas)}</row>')
        parte_hojas[f"xl/worksheets/sheet{n}.xml"] = (
            f'<worksheet xmlns="{NS}"><sheetData>{"".join(filas_xml)}</sheetData></worksheet>'
        )
        ids.append(f'<sheet name="{nombre}" sheetId="{n}" r:id="rId{n}"/>')
        rels.append(f'<Relationship Id="rId{n}" Type="x" Target="worksheets/sheet{n}.xml"/>')
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{NS}" xmlns:r="{NS_R}"><sheets>{"".join(ids)}</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="{NS_PKG}">{"".join(rels)}</Relationships>')
        for ruta, xml in parte_hojas.items():
            z.writestr(ruta, xml)
        if compartidas:
            z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{NS}">{"".join(f"<si><t>{t}</t></si>" for t in textos)}</sst>')
    return memoria.getvalue()


CABECERA = {0: "MÓDULO", 5: "UNIDAD DIDÁCTICA", 7: "CRÉDITO TEÓRICO", 8: "CRÉDITO PRÁCTICO", 9: "T. CRÉDITOS"}


def organizacion(curso="COCINA CRIOLLA", **extra):
    filas = {
        2: {0: "Denominación del programa de estudios", 4: curso} if curso else {0: "Otra cosa"},
        8: CABECERA,
        9: {0: "ATENCIÓN DE INCIDENTES", 5: "Soporte de hardware", 7: "2", 8: "2", 9: "4"},
        10: {5: "Redes   locales", 7: "1", 8: "3", 9: "4"},
        11: {1: "Experiencias formativas en situaciones reales de trabajo", 7: "0", 8: "3", 9: "3"},
        12: {0: "MANTENIMIENTO DE REDES", 5: "Cableado", 7: "3", 8: "1", 9: "4"},
        13: {0: "Orientaciones para la evaluación"},
        14: {0: "MÓDULO FANTASMA", 5: "Ignorado", 9: "4"},
    }
    filas.update(extra)
    return filas


def plan_subido(nombre="plan.xlsx", **kw):
    return SimpleUploadedFile(
        nombre,
        libro(
            {
                "Programa de estudio": {3: {0: "Denominación del programa de estudios", 3: "Soporte Técnico"}},
                "Organización modular": organizacion(**kw),
            }
        ),
    )


@pytest.fixture
def docente_2(db):
    return Usuario.objects.create_user(
        correo="pedro@cetpro.com", nombres="Pedro", apellidos="Rojas", password=CLAVE, rol=Rol.DOCENTE
    )


# ===================================================================== Leer el Excel


def leer(**kw):
    return plan_estudios.leer(io.BytesIO(libro({"Organización modular": organizacion(**kw)})))


def test_leer_el_plan():
    plan = leer()
    assert plan["curso"] == "COCINA CRIOLLA" and plan["avisos"] == []
    uno, dos = plan["modulos"]
    assert (uno["modulo"], uno["nombre"], uno["creditos"], uno["horas"]) == ("Módulo 1", "Atención de incidentes", 11, 304)
    assert uno["unidades"] == [
        {"nombre": "Soporte de hardware", "creditos": 4, "horas": 96},  # 2 teóricos × 16 + 2 prácticos × 32
        {"nombre": "Redes locales", "creditos": 4, "horas": 112},
        {"nombre": "Experiencias formativas en situaciones reales de trabajo (EFSRT)", "creditos": 3, "horas": 96},
    ]
    assert (dos["modulo"], dos["nombre"], dos["creditos"], dos["horas"]) == ("Módulo 2", "Mantenimiento de redes", 4, 80)
    assert len(plan["modulos"]) == 2  # lo que sigue a «Orientaciones» no cuenta


def test_el_curso_se_busca_en_la_hoja_programa_de_estudio_si_no_esta_en_la_modular():
    archivo = libro(
        {
            "Programa de estudio": {3: {0: "Denominación del programa de estudios", 3: "Peluquería y Barbería"}},
            "Organización modular": organizacion(curso=None),
        }
    )
    assert plan_estudios.leer(io.BytesIO(archivo))["curso"] == "Peluquería y Barbería"
    assert leer(curso=None)["curso"] == ""  # ninguna hoja lo dice


def test_numeros_con_coma_y_total_vacio():
    filas = {
        9: {0: "MÓDULO UNO", 5: "Con coma", 7: "1,5", 8: "2,5", 9: "4,0"},
        10: {5: "Sin total", 7: "2", 8: "1"},
        11: {5: "Sin créditos", 9: "0"},
        12: {5: "Texto raro", 7: "abc", 9: "xyz"},
    }
    plan = (
        leer(
            **{str(k): v for k, v in {}.items()},
        )
        if False
        else plan_estudios.leer(io.BytesIO(libro({"Organización modular": {8: CABECERA, **filas}})))
    )
    unidades = plan["modulos"][0]["unidades"]
    assert unidades == [
        {"nombre": "Con coma", "creditos": 4, "horas": 104},  # 1.5×16 + 2.5×32 = 104
        {"nombre": "Sin total", "creditos": 3, "horas": 64},  # total = teórico + práctico = 3; 2×16 + 1×32
    ]


def test_los_titulos_pueden_estar_en_otras_columnas():
    cabecera = {0: "Módulo", 2: "Unidad didáctica (UD)", 3: "Crédito teórico", 4: "Crédito práctico", 6: "Total créditos"}
    filas = {5: cabecera, 6: {0: "MÓDULO A", 2: "Otra unidad", 3: "1", 4: "1", 6: "2"}}
    plan = plan_estudios.leer(io.BytesIO(libro({"Organización modular": filas})))
    assert plan["modulos"][0]["unidades"] == [{"nombre": "Otra unidad", "creditos": 2, "horas": 48}]


def test_un_modulo_con_mas_de_12_unidades_avisa():
    filas = {8: CABECERA, 9: {0: "MÓDULO GRANDE", 5: "Unidad 1", 9: "2", 7: "1"}}
    filas.update({9 + n: {5: f"Unidad {n + 1}", 9: "2", 7: "1"} for n in range(1, 15)})
    plan = plan_estudios.leer(io.BytesIO(libro({"Organización modular": filas})))
    assert len(plan["modulos"][0]["unidades"]) == UnidadDidactica.MAX
    assert plan["avisos"] == ["El módulo 1 tiene más de 12 unidades: solo se tomaron las primeras 12."]


def test_se_toman_hasta_6_modulos_y_se_saltan_los_vacios():
    filas = {8: CABECERA}
    fila = 9
    for n in range(1, 9):
        filas[fila] = {0: f"MÓDULO {n}", 5: f"Unidad {n}", 9: "2", 7: "1"}
        filas[fila + 1] = {0: f"BLOQUE VACÍO {n}"}
        fila += 2
    plan = plan_estudios.leer(io.BytesIO(libro({"Organización modular": filas})))
    assert [m["modulo"] for m in plan["modulos"]] == [f"Módulo {n}" for n in range(1, 7)]


def test_errores_al_leer():
    with pytest.raises(ImportadorError, match="No encontré la hoja «Organización modular»"):
        plan_estudios.leer(io.BytesIO(libro({"Otra hoja": {1: {0: "x"}}})))
    with pytest.raises(ImportadorError, match="No encontré módulos con unidades didácticas"):
        plan_estudios.leer(io.BytesIO(libro({"Organización modular": {1: {0: "Nada que ver"}}})))
    with pytest.raises(ImportadorError, match="No encontré módulos"):
        plan_estudios.leer(io.BytesIO(libro({"Organización modular": {8: CABECERA}})))  # solo los títulos
    with pytest.raises(ImportadorError, match="No pudimos abrir el Excel"):
        plan_estudios.leer(io.BytesIO(b"no es excel"))


def test_nombres_de_hoja_con_guion_bajo_y_sin_tildes():
    archivo = libro({"Organizacion_modular": organizacion()})
    assert plan_estudios.leer(io.BytesIO(archivo))["modulos"]


# ===================================================================== Pantallas


def test_paso_1_subir(cliente_de, admin, docente):
    for quien, volver in ((admin, reverse("academico:admin_cursos")), (docente, reverse("academico:modulos"))):
        html = cliente_de(quien).get(reverse("academico:plan")).content.decode()
        assert (
            "Cargar plan de estudios" in html
            and "Sube el plan de estudios en Excel" in html
            and "Leer el plan" in html
            and volver in html
        )


def test_solo_administrador_y_docente(cliente_de, alumno):
    from django.test import Client

    assert cliente_de(alumno).get(reverse("academico:plan")).status_code == 403
    assert cliente_de(alumno).post(reverse("academico:plan"), {}).status_code == 403
    assert Client().get(reverse("academico:plan"))["Location"] == reverse("cuentas:login")


@pytest.mark.parametrize(
    ("archivo", "mensaje"),
    [
        (None, "Elige el archivo de Excel del plan de estudios."),
        (SimpleUploadedFile("plan.pdf", b"x"), "Sube el plan de estudios como archivo de Excel (.xlsx)."),
        (SimpleUploadedFile("plan.xlsx", libro({"Otra": {1: {0: "x"}}})), "No encontré la hoja «Organización modular»."),
        (SimpleUploadedFile("plan.xlsx", b"no es un excel"), "No pudimos abrir el Excel."),
    ],
)
def test_paso_1_errores(cliente_de, admin, archivo, mensaje):
    c = cliente_de(admin)
    r = c.post(reverse("academico:plan"), {"archivo": archivo} if archivo else {})
    assert r["Location"] == reverse("academico:plan") and mensaje in c.get(r["Location"]).content.decode()
    assert "_plan" not in c.session


def test_paso_1_archivo_muy_pesado(cliente_de, admin, settings):
    settings.ARCHIVOS_MAX_MB = 1
    c = cliente_de(admin)
    r = c.post(reverse("academico:plan"), {"archivo": SimpleUploadedFile("plan.xlsx", b"x" * (1024 * 1024 + 5))})
    assert "El archivo es muy pesado (máximo 1 MB)." in c.get(r["Location"]).content.decode()


def test_paso_2_revisar(cliente_de, admin, docente):
    c = cliente_de(admin)
    r = c.post(reverse("academico:plan"), {"archivo": plan_subido()})
    assert r["Location"] == reverse("academico:plan_revisar")
    html = c.get(r["Location"]).content.decode()
    assert "Encontré <b>2 módulos</b> en el curso «COCINA CRIOLLA»: 15 créditos y 384 horas en total." in html
    assert "Módulo 1 · Atención de incidentes" in html and "Soporte de hardware" in html and "4 créditos · 96 horas" in html
    assert "3 unidades didácticas" in html and "Cargar los módulos marcados" in html and "Subir otro archivo" in html
    assert "Crear el curso «COCINA CRIOLLA»" in html and "Torres, María" in html  # el administrador elige el docente
    assert html.count('name="usar[') == 2 and "checked" in html


def test_paso_2_sin_archivo_vuelve_al_paso_1(cliente_de, admin):
    c = cliente_de(admin)
    r = c.get(reverse("academico:plan_revisar"))
    assert (
        r["Location"] == reverse("academico:plan")
        and "Primero sube el archivo del plan de estudios." in c.get(r["Location"]).content.decode()
    )
    r = c.post(reverse("academico:plan_crear"), {"curso": "x"})
    assert "El archivo ya no está cargado. Súbelo otra vez." in c.get(r["Location"]).content.decode()


def test_el_curso_del_archivo_que_ya_existe_se_elige_solo(cliente_de, admin):
    c = cliente_de(admin)
    subir_plan(c)  # un curso que todavía no existe
    assert "Crear el curso «COCINA CRIOLLA»" in c.get(reverse("academico:plan_revisar")).content.decode()
    subir_plan(c, curso="SOPORTE TÉCNICO")  # ya está en la lista (sin mirar mayúsculas ni tildes)
    html = c.get(reverse("academico:plan_revisar")).content.decode()
    assert "Crear el curso" not in html and "<option selected>Soporte Técnico</option>" in html


# ===================================================================== Crear y completar


def subir_plan(c, **kw):
    c.post(reverse("academico:plan"), {"archivo": plan_subido(**kw)})


def datos(docente, **cambio):
    base = {"curso": "__nuevo__", "periodo": "2026-II", "usar[0]": "1", "usar[1]": "1", "destino[0]": "nuevo", "destino[1]": "nuevo",
            "docente[0]": docente.pk, "docente[1]": docente.pk, "turno[0]": "mañana", "turno[1]": "noche", "horario[0]": "Lunes a viernes", "horario[1]": ""}  # fmt: skip
    base.update(cambio)
    return {k: v for k, v in base.items() if v is not None}


def test_crear_los_modulos_y_el_curso(cliente_de, admin, docente):
    c = cliente_de(admin)
    subir_plan(c)
    r = c.post(reverse("academico:plan_crear"), datos(docente))
    assert r["Location"] == reverse("academico:admin_cursos")
    assert "Plan cargado en «COCINA CRIOLLA»: 2 módulos creados." in c.get(r["Location"]).content.decode()
    uno, dos = Modulo.objects.order_by("id")
    assert (uno.nombre, uno.especialidad, uno.modulo, uno.periodo, uno.turno, uno.horario, uno.docente) == (
        "Atención de incidentes", "COCINA CRIOLLA", "Módulo 1", "2026-II", "mañana", "Lunes a viernes", docente,
    )  # fmt: skip
    assert dos.turno == "noche" and uno.codigo and uno.codigo != dos.codigo
    assert [(u.nombre, u.creditos, u.horas) for u in uno.unidades_didacticas.all()][0] == ("Soporte de hardware", 4, 96)
    assert uno.unidades_didacticas.count() == 3 and dos.unidades_didacticas.count() == 1
    assert "COCINA CRIOLLA" in ajustes.nombres_especialidades()
    assert ajustes.color_curso("COCINA CRIOLLA") == "#1249A3"
    assert "_plan" not in c.session
    assert Registro.objects.filter(
        accion="modulo", detalle__contains="cargó el plan de estudios de «COCINA CRIOLLA»: 2 módulos nuevos y 0 completados"
    ).exists()


def test_cargar_solo_los_modulos_marcados(cliente_de, admin, docente):
    c = cliente_de(admin)
    subir_plan(c)
    c.post(reverse("academico:plan_crear"), datos(docente, **{"usar[1]": None}))
    assert Modulo.objects.count() == 1 and Modulo.objects.get().modulo == "Módulo 1"


def test_completar_un_modulo_que_ya_existe(cliente_de, admin, docente):
    existente = Modulo.crear(
        nombre="Mi módulo", especialidad="Peluquería y Barbería", periodo="2026-I", turno="tarde", docente=docente
    )
    UnidadDidactica.guardar_lista(existente, [{"nombre": "Vieja", "creditos": 1, "horas": 16}])
    c = cliente_de(admin)
    subir_plan(c, curso="SOPORTE TÉCNICO")
    existente.especialidad = "Soporte Técnico"
    existente.save()
    html = c.get(reverse("academico:plan_revisar")).content.decode()
    assert f'<option value="{existente.pk}"' in html and "Completar el que ya existe: Mi módulo · tarde · Prof. Torres" in html
    r = c.post(reverse("academico:plan_crear"), {"curso": "Soporte Técnico", "usar[0]": "1", "destino[0]": existente.pk})
    assert "Plan cargado en «Soporte Técnico»: 1 módulo completado." in c.get(r["Location"]).content.decode()
    assert Modulo.objects.count() == 1 and [u.nombre for u in existente.unidades_didacticas.all()][0] == "Soporte de hardware"
    assert existente.unidades_didacticas.count() == 3  # reemplazó a la «Vieja»
    # mezclado: uno se completa y el otro se crea
    subir_plan(c, curso="SOPORTE TÉCNICO")
    r = c.post(
        reverse("academico:plan_crear"),
        {
            "curso": "Soporte Técnico",
            "usar[0]": "1",
            "usar[1]": "1",
            "destino[0]": existente.pk,
            "destino[1]": "nuevo",
            "periodo": "2026-II",
            "turno[1]": "noche",
            "docente[1]": docente.pk,
        },
    )
    assert "1 módulo creado y 1 módulo completado." in c.get(r["Location"]).content.decode()


@pytest.mark.parametrize(
    ("cambio", "mensaje"),
    [
        ({"curso": ""}, "Elige el curso al que pertenece el plan."),
        ({"curso": "Un curso inventado"}, "Elige el curso al que pertenece el plan."),
        ({"periodo": ""}, "Para crear «Módulo 1» escribe el periodo y elige el turno."),
        ({"turno[0]": ""}, "Para crear «Módulo 1» escribe el periodo y elige el turno."),
        ({"turno[0]": "madrugada"}, "Para crear «Módulo 1» escribe el periodo y elige el turno."),
        ({"docente[0]": ""}, "Elige el docente de «Módulo 1»."),
        ({"docente[0]": 99999}, "Elige el docente de «Módulo 1»."),
        ({"usar[0]": None, "usar[1]": None}, "Marca al menos un módulo para cargar."),
        ({"destino[0]": "99999"}, "Elige un módulo de tu lista para completar «Módulo 1»."),
        ({"destino[0]": "abc"}, "Elige un módulo de tu lista para completar «Módulo 1»."),
    ],
)
def test_crear_con_datos_incorrectos(cliente_de, admin, docente, cambio, mensaje):
    c = cliente_de(admin)
    subir_plan(c)
    r = c.post(reverse("academico:plan_crear"), datos(docente, **cambio))
    assert r["Location"] == reverse("academico:plan_revisar")
    assert mensaje in c.get(r["Location"]).content.decode()
    assert not Modulo.objects.exists() and "COCINA CRIOLLA" not in ajustes.nombres_especialidades()  # nunca queda algo a medias
    assert "_plan" in c.session


def test_el_docente_elegido_debe_ser_docente(cliente_de, admin, alumno):
    c = cliente_de(admin)
    subir_plan(c)
    r = c.post(reverse("academico:plan_crear"), datos(alumno))
    assert "Elige el docente de «Módulo 1»." in c.get(r["Location"]).content.decode() and not Modulo.objects.exists()


def test_al_volver_con_error_conserva_lo_elegido(cliente_de, admin, docente):
    c = cliente_de(admin)
    subir_plan(c)
    r = c.post(reverse("academico:plan_crear"), datos(docente, **{"turno[0]": "", "horario[0]": "Lunes", "usar[1]": None}))
    assert r["Location"] == reverse("academico:plan_revisar")
    html = c.get(r["Location"]).content.decode()
    assert (
        'value="Lunes"' in html
        and f'<option value="{docente.pk}" selected>' in html
        and '<option value="noche" selected>' in html
    )
    assert re.search(r'name="usar\[0\]" value="1" checked', html) and not re.search(r'name="usar\[1\]" value="1" checked', html)


def test_el_docente_solo_trabaja_con_sus_modulos(cliente_de, docente, docente_2):
    mio = Modulo.crear(nombre="Mío", especialidad="Soporte Técnico", periodo="2026-II", turno="tarde", docente=docente)
    ajeno = Modulo.crear(nombre="Ajeno", especialidad="Soporte Técnico", periodo="2026-II", turno="tarde", docente=docente_2)
    c = cliente_de(docente)
    subir_plan(c, curso="SOPORTE TÉCNICO")
    html = c.get(reverse("academico:plan_revisar")).content.decode()
    assert "Completar el que ya existe: Mío" in html and "Ajeno" not in html and 'name="docente[' not in html  # no elige docente
    r = c.post(reverse("academico:plan_crear"), {"curso": "Soporte Técnico", "usar[0]": "1", "destino[0]": ajeno.pk})
    assert "Elige un módulo de tu lista para completar «Módulo 1»." in c.get(r["Location"]).content.decode()
    assert ajeno.unidades_didacticas.count() == 0
    r = c.post(
        reverse("academico:plan_crear"),
        {
            "curso": "Soporte Técnico",
            "usar[0]": "1",
            "usar[1]": "1",
            "destino[0]": mio.pk,
            "destino[1]": "nuevo",
            "periodo": "2026-II",
            "turno[1]": "noche",
        },
    )
    assert r["Location"] == reverse("academico:modulos")
    assert mio.unidades_didacticas.count() == 3
    nuevo = Modulo.objects.exclude(pk__in=[mio.pk, ajeno.pk]).get()
    assert nuevo.docente == docente and nuevo.turno == "noche"  # el nuevo queda a su cargo


def test_el_docente_no_puede_crear_cursos(cliente_de, docente):
    c = cliente_de(docente)
    subir_plan(c)
    html = c.get(reverse("academico:plan_revisar")).content.decode()
    assert "Crear el curso" not in html and "pídele al administrador que lo cree" in html
    for curso in ("__nuevo__", "COCINA CRIOLLA", ""):
        r = c.post(
            reverse("academico:plan_crear"),
            {"curso": curso, "usar[0]": "1", "destino[0]": "nuevo", "periodo": "2026-II", "turno[0]": "noche"},
        )
        assert (
            "Ese curso todavía no existe. Pídele al administrador que lo cree o que cargue el plan."
            in c.get(r["Location"]).content.decode()
        )
    assert not Modulo.objects.exists() and "COCINA CRIOLLA" not in ajustes.nombres_especialidades()


def test_el_curso_nuevo_no_se_repite(cliente_de, admin, docente):
    c = cliente_de(admin)
    ajustes.guardar_especialidades([*ajustes.especialidades(), {"nombre": "COCINA CRIOLLA", "color": "#ABCDEF", "foto": None}])
    subir_plan(c)
    c.post(reverse("academico:plan_crear"), datos(docente))
    assert ajustes.nombres_especialidades().count("COCINA CRIOLLA") == 1 and ajustes.color_curso("COCINA CRIOLLA") == "#ABCDEF"


def test_dos_veces_el_mismo_plan_crea_modulos_con_codigos_distintos(cliente_de, admin, docente):
    c = cliente_de(admin)
    for _ in range(2):
        subir_plan(c)
        c.post(reverse("academico:plan_crear"), datos(docente))
    codigos = list(Modulo.objects.values_list("codigo", flat=True))
    assert len(codigos) == 4 and len(set(codigos)) == 4


# ===================================================================== Topes de seguridad al leer el Excel


def _zip_con_hoja(xml, codificacion="utf-8"):
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zip_:
        zip_.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{NS}" xmlns:r="{NS_R}"><sheets><sheet name="Hoja" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        zip_.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{NS_PKG}"><Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        zip_.writestr("xl/worksheets/sheet1.xml", xml.encode(codificacion))
    z.seek(0)
    return z


def test_cada_parte_del_libro_tiene_un_tope():
    from apps.nucleo.importador import LibroXlsx

    archivo = io.BytesIO(libro({"Hoja": {1: {0: "x"}}}))
    with LibroXlsx(archivo, max_bytes=50) as lib, pytest.raises(ImportadorError, match="demasiado grande"):
        lib.hojas()


def test_el_libro_completo_tiene_un_tope_total():
    from apps.nucleo.importador import LibroXlsx

    archivo = io.BytesIO(libro({"Hoja": {1: {0: "x"}}}))
    with LibroXlsx(archivo, max_bytes=10_000, max_total=100) as lib, pytest.raises(ImportadorError, match="demasiado grande"):
        lib.hojas()  # cada parte es chica, pero juntas pasan del tope (una zip bomba con muchas partes)


def test_una_hoja_no_puede_tener_demasiadas_filas():
    from apps.nucleo.importador import LibroXlsx

    filas = {n: {0: f"fila {n}"} for n in range(1, 31)}
    with LibroXlsx(io.BytesIO(libro({"Hoja": filas}))) as lib:
        ruta = lib.hojas()["Hoja"]
        assert len(lib.filas(ruta)) == 30
        with pytest.raises(ImportadorError, match="demasiadas filas"):
            lib.filas(ruta, max_filas=10)


def test_la_hoja_con_dtd_se_rechaza_al_leerla_por_partes():
    from apps.nucleo.importador import LibroXlsx

    ataque = f'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><worksheet xmlns="{NS}"><sheetData/></worksheet>'
    for codificacion in ("utf-8", "utf-16"):
        xml = (
            ataque
            if codificacion == "utf-8"
            else ataque.replace('<?xml version="1.0"?>', '<?xml version="1.0" encoding="UTF-16"?>')
        )
        with LibroXlsx(_zip_con_hoja(xml, codificacion)) as lib, pytest.raises(ImportadorError, match="no es válido"):
            lib.filas(lib.hojas()["Hoja"])


def test_hoja_rota_o_que_no_esta():
    from apps.nucleo.importador import LibroXlsx

    with LibroXlsx(_zip_con_hoja("<worksheet><sheetData><row>")) as lib, pytest.raises(ImportadorError, match="dañado"):
        lib.filas(lib.hojas()["Hoja"])
    with LibroXlsx(_zip_con_hoja("<a/>")) as lib, pytest.raises(ImportadorError, match="dañado o incompleto"):
        lib.filas("xl/worksheets/no-existe.xml")


def test_el_plan_con_una_hoja_enorme_se_rechaza(monkeypatch):
    monkeypatch.setattr(plan_estudios, "MAX_BYTES_XML", 300)  # un tope chico para no armar un archivo gigante
    with pytest.raises(ImportadorError, match="demasiado grande"):
        plan_estudios.leer(io.BytesIO(libro({"Organización modular": organizacion()})))
