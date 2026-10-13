"""Importar preguntas desde texto de una IA, CSV, Excel o Word (y leer tablas de Excel para otras cargas)."""

import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.formularios.models import Formulario, Intento, Pregunta
from apps.nucleo import importador
from apps.nucleo.importador import ImportadorError, desde_archivo, desde_texto, filas_tabla

from .formularios_comun import nuevo_formulario, pregunta, responder, respuestas_correctas

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def una(texto, examen=True):
    r = desde_texto(texto, examen)
    assert r["errores"] == [], r["errores"]
    assert len(r["preguntas"]) == 1
    return r["preguntas"][0]


# ===================================================================== Texto


def test_pregunta_de_opciones_con_su_respuesta():
    p = una(
        "1. ¿Qué herramienta se usa para desenredar?\na) Navaja\nb) Peine de dientes anchos\nc) Secadora\nRespuesta: b\nPuntos: 2\nExplicación: El ancho no rompe."
    )
    assert p["tipo"] == "opcion" and p["enunciado"] == "¿Qué herramienta se usa para desenredar?"
    assert p["opciones"] == [
        ["Navaja", False, "opcion"],
        ["Peine de dientes anchos", True, "opcion"],
        ["Secadora", False, "opcion"],
    ]
    assert p["puntos"] == 2 and p["explicacion"] == "El ancho no rompe." and p["obligatoria"] == 1


@pytest.mark.parametrize(
    "linea", ["b) Peine *", "b) Peine (correcta)", "b) Peine (Correcto)", "b) Peine ✓", "b) Peine ✔", "b. Peine *", "B- Peine *"]
)
def test_la_correcta_se_puede_marcar_en_la_opcion(linea):
    p = una(f"1. Pregunta\na) Navaja\n{linea}\nc) Secadora")
    assert [o[1] for o in p["opciones"]] == [False, True, False] and p["opciones"][1][0] == "Peine"


def test_formas_de_decir_la_respuesta():
    for escrito in ("Respuesta: b", "respuesta correcta - b", "Correcta: B", "Clave: b"):
        p = una(f"1. Pregunta\na) Uno\nb) Dos\n{escrito}")
        assert [o[1] for o in p["opciones"]] == [False, True], escrito


def test_varias_correctas_son_casillas():
    p = una("1. ¿Cuáles son de bioseguridad?\na) Guantes\nb) Mascarilla\nc) Anillos\nRespuesta: a, b")
    assert p["tipo"] == "multiple" and [o[1] for o in p["opciones"]] == [True, True, False]
    p = una("1. ¿Cuáles son?\na) Guantes\nb) Mascarilla\nc) Anillos\nRespuesta: a y b")
    assert p["tipo"] == "multiple"
    p = una("1. ¿Cuáles son?\na) Guantes *\nb) Mascarilla *\nc) Anillos")
    assert p["tipo"] == "multiple"


def test_verdadero_o_falso():
    p = una("1. La tijera se desinfecta.\na) Verdadero\nb) Falso\nRespuesta: a")
    assert p["tipo"] == "vf" and p["opciones"] == [["Verdadero", True, "opcion"], ["Falso", False, "opcion"]]
    p = una("1. La tijera se desinfecta.\na) Verdadero\nb) Falso *")
    assert p["opciones"] == [["Verdadero", False, "opcion"], ["Falso", True, "opcion"]]
    p = una("1. La tijera se desinfecta.\nRespuesta: Falso")
    assert p["tipo"] == "vf" and p["opciones"][1][1] is True
    p = una("1. Es seguro.\na) Verdadero\nb) Falso\nRespuesta: Verdadero")
    assert p["opciones"][0][1] is True


def test_respuesta_corta_y_parrafo():
    p = una("1. ¿Cómo se llama el corte gradual?\nRespuesta: degrafilado | degradado")
    assert p["tipo"] == "corta" and p["aceptadas"] == "degrafilado\ndegradado" and p["opciones"] == []
    p = una("1. ¿Cómo se llama?\nRespuesta: degradado; degrafilado")
    assert p["aceptadas"] == "degradado\ndegrafilado"
    p = una("1. Explica cómo recibes a un cliente.")
    assert p["tipo"] == "abierta" and p["aceptadas"] is None and p["puntos"] == 1


def test_puntos_con_coma_y_limites():
    assert una("1. Pregunta\nRespuesta: algo\nPuntos: 2,5")["puntos"] == 2.5
    assert una("1. Pregunta\nRespuesta: algo\nPuntos: 500")["puntos"] == 100
    assert una("1. Pregunta\nRespuesta: algo")["puntos"] == 1


def test_la_pregunta_sigue_en_otra_linea():
    p = una("1. Esta pregunta es muy larga\ny sigue en la siguiente línea\na) Uno\nb) Dos\nRespuesta: a")
    assert p["enunciado"] == "Esta pregunta es muy larga y sigue en la siguiente línea"


def test_el_texto_de_antes_de_la_primera_pregunta_se_ignora():
    r = desde_texto(
        "¡Claro! Aquí tienes tus preguntas:\n\n**Examen**\n\n1. Pregunta\na) Uno\nb) Dos\nRespuesta: a\n\nEspero que te sirva.",
        True,
    )
    assert len(r["preguntas"]) == 1 and r["errores"] == []
    assert r["preguntas"][0]["opciones"][0] == ["Uno", True, "opcion"]


def test_se_limpia_el_formato_markdown():
    p = una("**1. ¿Qué es la bioseguridad?**\n- a) **Cuidarse**\n- b) Descuidarse\n> Respuesta: **a**")
    assert p["enunciado"] == "¿Qué es la bioseguridad?" and p["opciones"][0] == ["Cuidarse", True, "opcion"]


def test_numeracion_con_distintos_estilos():
    r = desde_texto("Pregunta 1: Uno\nRespuesta: a\n2) Dos\nRespuesta: b\n3 - Tres\nRespuesta: c\n4: Cuatro\nRespuesta: d", True)
    assert [p["enunciado"] for p in r["preguntas"]] == ["Uno", "Dos", "Tres", "Cuatro"]


def test_si_no_hay_numeros_cada_linea_con_signo_de_pregunta_es_una_pregunta():
    r = desde_texto(
        "¿Qué es un peine?\na) Un objeto\nb) Un animal\nRespuesta: a\n\n¿Qué es una tijera?\nRespuesta: una herramienta", True
    )
    assert [p["enunciado"] for p in r["preguntas"]] == ["¿Qué es un peine?", "¿Qué es una tijera?"]
    assert r["preguntas"][0]["tipo"] == "opcion" and r["preguntas"][1]["tipo"] == "corta"


def test_errores_de_preguntas_que_no_se_pudieron_leer():
    r = desde_texto(
        "1. Sin respuesta\na) Uno\nb) Dos\n2. Con una sola opción\na) Única\nRespuesta: a\n3. Verdadero o falso mal\na) Verdadero\nb) Falso\n4. Buena\nRespuesta: x",
        True,
    )
    assert r["errores"] == [
        "Pregunta 1: no dice cuál es la respuesta correcta (escribe «Respuesta: b» o marca la opción con *).",
        "Pregunta 2: necesita al menos 2 opciones.",
        "Pregunta 3: en verdadero o falso, la respuesta debe ser «Verdadero» o «Falso».",
    ]
    assert [p["enunciado"] for p in r["preguntas"]] == ["Buena"]


def test_sin_preguntas():
    r = desde_texto("Hola, esto no tiene preguntas.\nSolo texto suelto.", True)
    assert r["preguntas"] == [] and r["errores"] == [
        "No encontramos preguntas. Cada pregunta debe empezar con su número, por ejemplo: «1. ¿Qué es…?»."
    ]
    assert desde_texto("", True)["errores"]


def test_en_trabajos_y_encuestas_no_hay_correctas_ni_puntos():
    r = desde_texto(
        "1. ¿Cómo te fue?\na) Bien\nb) Mal\n2. Verdadero o falso\na) Verdadero\nb) Falso\nRespuesta: a\nPuntos: 5\nExplicación: no se guarda",
        False,
    )
    assert r["errores"] == []
    opcion, vf = r["preguntas"]
    assert [o[1] for o in opcion["opciones"]] == [False, False] and opcion["puntos"] == 0 and opcion["aceptadas"] is None
    assert [o[1] for o in vf["opciones"]] == [False, False] and vf["puntos"] == 0 and vf["explicacion"] is None


def test_con_mas_de_cien_preguntas_se_leen_cien():
    texto = "\n".join(f"{n}. Pregunta {n}\nRespuesta: algo" for n in range(1, 131))
    assert len(desde_texto(texto, True)["preguntas"]) == 100


def test_una_pregunta_con_varias_correctas_marcadas_en_tipo_opcion_pasa_a_casillas():
    r = desde_texto("1. Elige\na) Uno *\nb) Dos *\nc) Tres", True)
    assert r["preguntas"][0]["tipo"] == "multiple"


# ===================================================================== CSV


def csv_subido(contenido, nombre="preguntas.csv", codificacion="utf-8"):
    return SimpleUploadedFile(nombre, contenido.encode(codificacion), content_type="text/csv")


PLANTILLA = (
    "Tipo;Pregunta;Opción A;Opción B;Opción C;Opción D;Correcta;Puntos;Obligatoria;Explicación\n"
    "opciones;¿Qué se usa para desenredar?;Navaja;Peine ancho;Secadora;;B;2;sí;El ancho no rompe.\n"
    "casillas;¿Cuáles son de bioseguridad?;Guantes;Mascarilla;Anillos;Capa;A,B,D;3;sí;\n"
    "vf;La tijera se desinfecta.;;;;;Verdadero;1;sí;\n"
    "corta;¿Cómo se llama el corte?;;;;;degrafilado | degradado;2;sí;\n"
    "parrafo;Explica cómo recibes a un cliente.;;;;;;2;no;\n"
    "desplegable;¿En qué turno estudias?;Mañana;Tarde;Noche;;;0;sí;\n"
)


def test_plantilla_de_csv():
    r = desde_archivo(csv_subido("﻿" + PLANTILLA), "preguntas.csv", True)
    assert r["errores"] == []
    opcion, casillas, vf, corta, parrafo, desplegable = r["preguntas"]
    assert opcion["tipo"] == "opcion" and opcion["opciones"][1] == ["Peine ancho", True, "opcion"] and opcion["puntos"] == 2
    assert opcion["explicacion"] == "El ancho no rompe."
    assert (
        casillas["tipo"] == "multiple"
        and [o[1] for o in casillas["opciones"]] == [True, True, False, True]
        and casillas["puntos"] == 3
    )
    assert vf["tipo"] == "vf" and vf["opciones"][0][1] is True
    assert corta["aceptadas"] == "degrafilado\ndegradado"
    assert parrafo["tipo"] == "abierta" and parrafo["obligatoria"] == 0
    assert desplegable["tipo"] == "desplegable" and desplegable["puntos"] == 0 and desplegable["opciones"][0][1] is False


def test_csv_con_comas_y_windows_1252():
    contenido = "Pregunta,Opción A,Opción B,Correcta\n¿Cuál es la capital?,Lima,Cusco,A\n"
    r = desde_archivo(csv_subido(contenido, codificacion="cp1252"), "x.csv", True)
    assert r["errores"] == [] and r["preguntas"][0]["opciones"][0] == ["Lima", True, "opcion"]


def test_columnas_en_cualquier_orden_y_con_otros_nombres():
    contenido = "Correcta;Alternativa A;Alternativa B;Enunciado;Puntaje\nb;Uno;Dos;La pregunta;4\n"
    r = desde_archivo(csv_subido(contenido), "x.csv", True)
    p = r["preguntas"][0]
    assert r["errores"] == [] and p["enunciado"] == "La pregunta" and p["puntos"] == 4 and p["opciones"][1][1] is True


def test_errores_en_las_filas_del_csv():
    contenido = (
        "Tipo;Pregunta;Opción A;Opción B;Correcta\nraro;Pregunta rara;a;b;A\nopciones;Solo una;a;;A\nopciones;Buena;a;b;B\n;;;;\n"
    )
    r = desde_archivo(csv_subido(contenido), "x.csv", True)
    assert r["errores"] == ["Fila 2: no conocemos el tipo «raro».", "Fila 3: necesita al menos 2 opciones."]
    assert [p["enunciado"] for p in r["preguntas"]] == ["Buena"]


def test_csv_sin_columna_de_pregunta_o_vacio():
    r = desde_archivo(csv_subido("Tipo;Otra\na;b\n"), "x.csv", True)
    assert r["errores"] == ["No encontramos la columna «Pregunta». Usa la plantilla (la primera fila debe tener los títulos)."]
    assert desde_archivo(csv_subido(""), "x.csv", True)["errores"] == ["El archivo está vacío."]


def test_archivo_de_texto_y_extensiones_no_permitidas():
    r = desde_archivo(io.BytesIO("1. Pregunta ñandú\nRespuesta: sí".encode("cp1252")), "preguntas.txt", True)
    assert r["preguntas"][0]["enunciado"] == "Pregunta ñandú"
    for nombre in ("virus.exe", "preguntas.pdf", "sin_extension"):
        with pytest.raises(ImportadorError, match="Sube un archivo de Excel"):
            desde_archivo(io.BytesIO(b"x"), nombre, True)


# ===================================================================== Excel


def xlsx(filas, compartidas=True, hoja_en="xl/worksheets/sheet1.xml", extra=None):
    """Arma un .xlsx mínimo con esas filas (la primera hoja)."""
    letras = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    textos, filas_xml = [], []
    for n, fila in enumerate(filas, start=1):
        celdas = []
        for i, valor in enumerate(fila):
            if valor is None:
                continue
            ref = f"{letras[i]}{n}"
            if isinstance(valor, (int, float)):
                celdas.append(f'<c r="{ref}"><v>{valor}</v></c>')
            elif compartidas:
                textos.append(valor)
                celdas.append(f'<c r="{ref}" t="s"><v>{len(textos) - 1}</v></c>')
            else:
                celdas.append(f'<c r="{ref}" t="inlineStr"><is><t>{valor}</t></is></c>')
        filas_xml.append(f'<row r="{n}">{"".join(celdas)}</row>')
    hoja = f'<worksheet xmlns="{NS}"><sheetData>{"".join(filas_xml)}</sheetData></worksheet>'
    libro = f'<workbook xmlns="{NS}" xmlns:r="{NS_R}"><sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    destino = hoja_en.removeprefix("xl/")
    rels = f'<Relationships xmlns="{NS_PKG}"><Relationship Id="rId1" Type="x" Target="{destino}"/></Relationships>'
    compartidas_xml = f'<sst xmlns="{NS}">{"".join(f"<si><t>{t}</t></si>" for t in textos)}</sst>'
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as z:
        z.writestr("xl/workbook.xml", libro)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr(hoja_en, hoja)
        if compartidas:
            z.writestr("xl/sharedStrings.xml", compartidas_xml)
        for nombre, contenido in (extra or {}).items():
            z.writestr(nombre, contenido)
    memoria.seek(0)
    return memoria


CABECERA = ["Tipo", "Pregunta", "Opción A", "Opción B", "Correcta", "Puntos"]


@pytest.mark.parametrize("compartidas", [True, False])
def test_excel_con_cadenas_compartidas_o_en_la_celda(compartidas):
    filas = [CABECERA, ["opciones", "¿Cuál?", "Uno", "Dos", "B", 3], ["vf", "Es verdad", None, None, "Falso", 1.5]]
    r = desde_archivo(xlsx(filas, compartidas), "p.xlsx", True)
    assert r["errores"] == []
    opcion, vf = r["preguntas"]
    assert opcion["opciones"][1] == ["Dos", True, "opcion"] and opcion["puntos"] == 3
    assert vf["tipo"] == "vf" and vf["opciones"][1][1] is True and vf["puntos"] == 1.5


def test_excel_toma_la_hoja_que_dice_el_libro():
    filas = [CABECERA, ["opciones", "En otra hoja", "A", "B", "A", 1]]
    r = desde_archivo(xlsx(filas, hoja_en="xl/worksheets/sheet7.xml"), "p.xlsx", True)
    assert r["preguntas"][0]["enunciado"] == "En otra hoja"


def test_excel_con_celdas_vacias_al_inicio_de_la_fila():
    filas = [["", "Pregunta"], [None, "Solo la columna B"]]
    assert desde_archivo(xlsx(filas), "p.xlsx", True)["preguntas"][0]["enunciado"] == "Solo la columna B"


def test_excel_dañado_o_que_no_es_excel():
    with pytest.raises(ImportadorError, match="No pudimos abrir el Excel"):
        desde_archivo(io.BytesIO(b"esto no es un zip"), "p.xlsx", True)
    vacio = io.BytesIO()
    with zipfile.ZipFile(vacio, "w") as z:
        z.writestr("otra/cosa.txt", "x")
    vacio.seek(0)
    with pytest.raises(ImportadorError, match="no tiene hojas con datos"):
        filas_tabla(vacio, "p.xlsx")


def test_excel_con_xml_roto():
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zip_:
        zip_.writestr("xl/worksheets/sheet1.xml", "<worksheet><sheetData><row>")
    z.seek(0)
    with pytest.raises(ImportadorError, match="dañado"):
        filas_tabla(z, "p.xlsx")


def test_excel_con_dtd_o_entidades_se_rechaza():
    ataque = f'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><worksheet xmlns="{NS}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&a;</t></is></c></row></sheetData></worksheet>'
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zip_:
        zip_.writestr("xl/worksheets/sheet1.xml", ataque)
    z.seek(0)
    with pytest.raises(ImportadorError, match="no es válido"):
        filas_tabla(z, "p.xlsx")


def test_el_ataque_en_utf16_tampoco_pasa():
    """Un XML en UTF-16 no tiene «<!DOCTYPE» en ASCII: lo detiene defusedxml."""
    ataque = f'<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY a "aaaa">]><worksheet xmlns="{NS}"><sheetData/></worksheet>'.encode(
        "utf-16"
    )
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zip_:
        zip_.writestr("xl/worksheets/sheet1.xml", ataque)
    z.seek(0)
    with pytest.raises(ImportadorError, match="no es válido"):
        filas_tabla(z, "p.xlsx")


def test_excel_demasiado_grande():
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zip_:
        zip_.writestr("xl/worksheets/sheet1.xml", "<a>" + "x" * (importador.MAX_BYTES_XML + 10) + "</a>")
    z.seek(0)
    with pytest.raises(ImportadorError, match="demasiado grande"):
        filas_tabla(z, "p.xlsx")


def test_tablas_de_excel_y_csv_tal_cual():
    assert filas_tabla(xlsx([["DNI", "Nombres"], ["12345678", "Rosa"], [None, "sin dni"]]), "alumnos.xlsx") == [
        ["DNI", "Nombres"], ["12345678", "Rosa"], ["", "sin dni"],
    ]  # fmt: skip
    assert filas_tabla(csv_subido("DNI;Nombres\n12345678;Rosa\n"), "a.csv") == [["DNI", "Nombres"], ["12345678", "Rosa"]]
    assert filas_tabla(csv_subido("DNI,Nombres\n1,Ana\n"), "a.txt") == [["DNI", "Nombres"], ["1", "Ana"]]
    with pytest.raises(ImportadorError, match="Sube un archivo de Excel"):
        filas_tabla(io.BytesIO(b"x"), "a.pdf")


# ===================================================================== Word


def docx(parrafos, extra_xml=""):
    cuerpo = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in parrafos)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{NS_W}"><w:body>{cuerpo}{extra_xml}</w:body></w:document>'
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zip_:
        zip_.writestr("word/document.xml", xml)
    z.seek(0)
    return z


def test_word_con_preguntas_numeradas():
    r = desde_archivo(
        docx(
            [
                "1. ¿Qué es la bioseguridad?",
                "a) Cuidarse",
                "b) Descuidarse",
                "Respuesta: a",
                "2. Tijera &amp; peine",
                "Respuesta: herramientas",
            ]
        ),
        "p.docx",
        True,
    )
    assert r["errores"] == [] and len(r["preguntas"]) == 2
    assert r["preguntas"][0]["opciones"][0] == ["Cuidarse", True, "opcion"] and r["preguntas"][1]["enunciado"] == "Tijera & peine"


def test_word_con_lista_automatica_sin_numeros():
    r = desde_archivo(
        docx(
            ["¿Qué es un peine?", "a) Un objeto", "b) Un animal", "Respuesta: a", "¿Qué es una tijera?", "Respuesta: herramienta"]
        ),
        "p.docx",
        True,
    )
    assert [p["enunciado"] for p in r["preguntas"]] == ["¿Qué es un peine?", "¿Qué es una tijera?"]


def test_word_con_tabulaciones_y_saltos():
    r = desde_archivo(docx(["1. Pregunta<w:tab/>con tab<w:br/>y salto", "Respuesta: x"]), "p.docx", True)
    assert r["preguntas"][0]["enunciado"] == "Pregunta con tab y salto"


def test_word_dañado_o_vacio():
    with pytest.raises(ImportadorError, match="No pudimos abrir el Word"):
        desde_archivo(io.BytesIO(b"no es zip"), "p.docx", True)
    vacio = io.BytesIO()
    with zipfile.ZipFile(vacio, "w") as z:
        z.writestr("otra.xml", "x")
    vacio.seek(0)
    with pytest.raises(ImportadorError, match="vacío o dañado"):
        desde_archivo(vacio, "p.docx", True)


# ===================================================================== Las pantallas de importar


def url(nombre, f):
    return reverse(f"formularios:{nombre}", args=[f.pk])


BUENAS = "1. ¿Qué se usa para desenredar?\na) Navaja\nb) Peine ancho\nc) Secadora\nRespuesta: b\nPuntos: 4\n2. ¿Cómo se llama el corte?\nRespuesta: degradado"


@pytest.fixture
def borrador(clase):
    return nuevo_formulario(clase, publicado=False)


def test_pantalla_de_importar(cliente_de, docente, modulo, clase, borrador):
    html = cliente_de(docente).get(url("importar", borrador)).content.decode()
    assert "Importar preguntas" in html and "1. Pide las preguntas a la IA" in html and "Peluquería – M1" in html
    assert "[ESCRIBE AQUÍ EL TEMA]" in html and 'name="archivo"' in html
    assert reverse("formularios:plantilla") in html and "Nada se guarda hasta que tú lo confirmes." in html


def test_revisar_y_agregar_las_preguntas(cliente_de, docente, modulo, clase, borrador):
    c = cliente_de(docente)
    r = c.post(url("importar", borrador), {"texto": BUENAS})
    html = r.content.decode()
    assert (
        r.status_code == 200 and "Revisa antes de agregar" in html and "Encontramos 2 preguntas. Revisa que estén bien." in html
    )
    assert (
        "Pregunta 1" in html
        and "Peine ancho" in html
        and "4 puntos" in html
        and "Respuesta correcta:" in html
        and "degradado" in html
    )
    assert "Agregar 2 preguntas al formulario" in html and "Corregir el texto y volver a leer" in html
    assert Pregunta.objects.count() == 0  # todavía no se guardó nada
    r = c.post(url("importar_confirmar", borrador))
    assert r["Location"] == url("ver", borrador)
    assert "2 preguntas agregadas. Revísalas y cambia lo que haga falta." in c.get(r["Location"]).content.decode()
    abierta, corta = Pregunta.objects.order_by("orden")[:2]
    assert (abierta.tipo, abierta.puntos, abierta.orden) == ("opcion", 4, 1) and corta.respuestas_aceptadas == "degradado"
    assert [(o.texto, o.correcta) for o in abierta.todas_las_opciones.all()] == [
        ("Navaja", False),
        ("Peine ancho", True),
        ("Secadora", False),
    ]
    # lo importado se agrega al final de lo que ya había
    c.post(url("importar", borrador), {"texto": "1. Otra\nRespuesta: x"})
    c.post(url("importar_confirmar", borrador))
    assert list(Pregunta.objects.order_by("orden").values_list("orden", flat=True)) == [1, 2, 3]
    assert c.post(url("importar_confirmar", borrador)).status_code == 302  # ya se usó: no se agrega dos veces
    assert Pregunta.objects.count() == 3


def test_importar_un_archivo(cliente_de, docente, modulo, clase, borrador):
    c = cliente_de(docente)
    r = c.post(url("importar", borrador), {"archivo": csv_subido(PLANTILLA)})
    html = r.content.decode()
    assert "Encontramos 6 preguntas." in html and "Agregar 6 preguntas al formulario" in html
    assert "Casillas (elige varias)" in html and "Lista desplegable" in html
    c.post(url("importar_confirmar", borrador))
    assert Pregunta.objects.count() == 6


def test_el_archivo_manda_sobre_el_texto(cliente_de, docente, modulo, clase, borrador):
    r = cliente_de(docente).post(
        url("importar", borrador), {"texto": "1. Del texto\nRespuesta: x", "archivo": csv_subido(PLANTILLA)}
    )
    assert "Encontramos 6 preguntas." in r.content.decode()


def test_importar_con_errores_en_algunas_preguntas(cliente_de, docente, modulo, clase, borrador):
    texto = "1. Buena\na) Uno\nb) Dos\nRespuesta: a\n2. Sin respuesta\na) Uno\nb) Dos"
    html = cliente_de(docente).post(url("importar", borrador), {"texto": texto}).content.decode()
    assert "Hay 1 pregunta que no pudimos leer" in html and "Pregunta 2: no dice cuál es la respuesta correcta" in html
    assert "Encontramos 1 pregunta. Revisa que estén bien." in html
    texto += "\n3. Otra sin respuesta\na) Uno\nb) Dos"
    html = cliente_de(docente).post(url("importar", borrador), {"texto": texto}).content.decode()
    assert "Hay 2 preguntas que no pudimos leer" in html


def test_importar_sin_nada_que_agregar(cliente_de, docente, modulo, clase, borrador):
    c = cliente_de(docente)
    html = c.post(url("importar", borrador), {"texto": "Solo texto suelto"}).content.decode()
    assert "No encontramos preguntas." in html and "al formulario" not in html  # no hay botón para agregar
    assert "Corregir el texto y volver a leer" in html and "Solo texto suelto" in html and "Empezar de nuevo" in html
    r = c.post(url("importar_confirmar", borrador))  # no hay nada guardado para agregar
    assert "No hay preguntas para agregar." in c.get(r["Location"]).content.decode() and Pregunta.objects.count() == 0


@pytest.mark.parametrize(
    ("datos", "mensaje"),
    [
        ({}, "Pega el texto con las preguntas o elige un archivo."),
        ({"texto": "   "}, "Pega el texto con las preguntas o elige un archivo."),
        (
            {"archivo": SimpleUploadedFile("virus.exe", b"MZ")},
            "Sube un archivo de Excel (.xlsx), CSV, Word (.docx) o de texto (.txt).",
        ),
        ({"archivo": SimpleUploadedFile("roto.xlsx", b"no es excel")}, "No pudimos abrir el Excel."),
    ],
)
def test_importar_con_problemas(cliente_de, docente, modulo, clase, borrador, datos, mensaje):
    r = cliente_de(docente).post(url("importar", borrador), datos)
    assert r.status_code == 200 and mensaje in r.content.decode() and "1. Pide las preguntas a la IA" in r.content.decode()


def test_importar_un_archivo_muy_pesado(cliente_de, docente, modulo, clase, borrador, settings):
    settings.ARCHIVOS_MAX_MB = 1
    grande = SimpleUploadedFile("grande.csv", b"x" * (1024 * 1024 + 10))
    r = cliente_de(docente).post(url("importar", borrador), {"archivo": grande})
    assert "No se pudo leer el archivo. Revisa que pese menos de 1 MB." in r.content.decode()


def test_confirmar_una_importacion_de_otro_formulario(cliente_de, docente, modulo, clase, borrador):
    otro = nuevo_formulario(clase, publicado=False, titulo="Otro")
    c = cliente_de(docente)
    c.post(url("importar", borrador), {"texto": BUENAS})
    r = c.post(url("importar_confirmar", otro))
    assert "No hay preguntas para agregar." in c.get(r["Location"]).content.decode() and Pregunta.objects.count() == 0


def test_en_una_encuesta_se_importa_sin_respuestas_correctas(cliente_de, docente, modulo, clase):
    f = nuevo_formulario(clase, modo="encuesta", publicado=False)
    c = cliente_de(docente)
    html = c.post(url("importar", f), {"texto": "1. ¿Cómo te fue?\na) Bien\nb) Mal"}).content.decode()
    assert "Encontramos 1 pregunta." in html and "puntos</span>" not in html and "punto</span>" not in html
    c.post(url("importar_confirmar", f))
    p = Pregunta.objects.get()
    assert p.puntos == 0 and not any(o.correcta for o in p.todas_las_opciones.all())


def test_no_se_importa_si_ya_hay_respuestas(cliente_de, docente, rosa, modulo, clase, examen):
    responder(cliente_de(rosa), examen, respuestas_correctas(examen))
    c = cliente_de(docente)
    for r in (
        c.get(url("importar", examen)),
        c.post(url("importar", examen), {"texto": BUENAS}),
        c.post(url("importar_confirmar", examen)),
    ):
        assert r.status_code == 302 and r["Location"] == url("ver", examen)
    assert Intento.objects.count() == 1 and Pregunta.objects.filter(formulario=examen).count() == 4


def test_solo_el_docente_importa(cliente_de, rosa, otro_docente, admin, modulo, clase, borrador):
    for quien in (rosa, otro_docente, admin):
        c = cliente_de(quien)
        assert c.get(url("importar", borrador)).status_code == 403
        assert c.post(url("importar", borrador), {"texto": BUENAS}).status_code == 403
        assert c.post(url("importar_confirmar", borrador)).status_code == 403
    assert Pregunta.objects.count() == 0 and Formulario.objects.count() == 1


def test_lo_importado_se_puede_usar_enseguida(cliente_de, docente, rosa, modulo, clase, borrador):
    pregunta(borrador, "seccion", "Parte 1", puntos=0)
    c = cliente_de(docente)
    c.post(url("importar", borrador), {"texto": BUENAS})
    c.post(url("importar_confirmar", borrador))
    c.post(url("publicar", borrador), {"publicar": "1"})
    i, _ = responder(
        cliente_de(rosa),
        borrador,
        {
            f"op[{p.pk}]": next(o.pk for o in p.opciones if o.correcta)
            for p in borrador.preguntas_completas()
            if p.tipo == "opcion"
        }
        | {f"txt[{p.pk}]": "Degradado" for p in borrador.preguntas_completas() if p.tipo == "corta"},
    )
    i.refresh_from_db()
    assert i.nota == 20 and i.puntaje_max == 5
