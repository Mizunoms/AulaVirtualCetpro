"""Prueba de importar preguntas (texto de IA, CSV, Excel .xlsx y Word .docx). Usa la base aula_virtual_pruebas."""

import io
import re
import zipfile
from xml.sax.saxutils import escape

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cliente import *  # noqa: E402,F401,F403  (Cliente, ok, fallos, png, PDF)
import subprocess


def sql(q):
    """Consulta de solo lectura a la base de aceptación (PostgreSQL); devuelve filas de textos como lo hacía mysql.exe."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")) as con:
        filas = con.execute(q).fetchall()
    return [["" if v is None else str(v) for v in f] for f in filas]


def xlsx(filas):
    """Excel mínimo real: con sharedStrings (como lo guarda Excel)."""
    textos = []

    def s(v):
        if v not in textos:
            textos.append(v)
        return textos.index(v)

    rows = []
    for r, fila in enumerate(filas, 1):
        celdas = "".join('<c r="%s%d" t="s"><v>%d</v></c>' % (chr(65 + c), r, s(v)) for c, v in enumerate(fila) if v != "")
        rows.append('<row r="%d">%s</row>' % (r, celdas))
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook %s xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Preguntas" sheetId="1" r:id="rId1"/></sheets></workbook>'
            % ns,
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="worksheet" Target="worksheets/hoja1.xml"/></Relationships>',
        )
        z.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0"?><sst %s>%s</sst>' % (ns, "".join("<si><t>%s</t></si>" % escape(t) for t in textos)),
        )
        z.writestr(
            "xl/worksheets/hoja1.xml",
            '<?xml version="1.0"?><worksheet %s><sheetData>%s</sheetData></worksheet>' % (ns, "".join(rows)),
        )
    return b.getvalue()


def docx(parrafos):
    cuerpo = "".join('<w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % escape(p) for p in parrafos)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>%s</w:body></w:document>'
            % cuerpo,
        )
    return b.getvalue()


doc = Cliente()
doc.login("rosa.paredes@cetpro.test", "20000001")
c, t, *_ = doc.post(
    "/cursos/1/examenes",
    {
        "modo": "examen",
        "titulo": "Importado",
        "fecha": "2030-01-01",
        "hora": "23:59",
        "intentos_max": "1",
        "mostrar_respuestas": "1",
    },
)
qid = re.search(r'action="[^"]*/examenes/(\d+)/preguntas"', t).group(1)
ok("Importar preguntas" in t, 'el editor ofrece "Importar preguntas"')
c, t, *_ = doc.get("/examenes/%s/importar" % qid)
ok(
    "Copiar instrucción" in t and "Peluquería y Barbería" in t and "Descargar plantilla" in t,
    "pantalla de importar con instrucción para la IA",
)

print("== Texto de la IA")
texto = """¡Claro! Aquí tienes las preguntas:

**1. ¿Qué herramienta se usa para desenredar el cabello?**
a) Navaja
b) Peine de dientes anchos
c) Secadora
Respuesta: b
Puntos: 2

2. Se debe desinfectar la tijera después de cada cliente.
a) Verdadero
b) Falso
Respuesta: a

3. ¿Cuáles son elementos de bioseguridad?
a) Guantes *
b) Anillos
c) Mascarilla *

4. ¿Cuál es el color primario?
a) Verde
b) Morado
"""
c, t, *_ = doc.post("/examenes/%s/importar" % qid, {"texto": texto})
ok(
    "Encontramos 3 preguntas" in t and "Pregunta 4" in t and "Agregar 3 preguntas" in t,
    "vista previa: 3 bien y avisa la que falla",
)
ok(sql("SELECT COUNT(*) FROM av_preguntas WHERE cuestionario_id = %s" % qid)[0][0] == "0", "todavía no guardó nada")
c, t, *_ = doc.post("/examenes/%s/importar/confirmar" % qid)
ok("3 preguntas agregadas" in t and "Peine de dientes anchos" in t, "confirma y se agregan al formulario")
c, t, *_ = doc.post("/examenes/%s/importar/confirmar" % qid)
ok("No hay preguntas para agregar" in t, "no se pueden agregar dos veces")

print("== Plantilla y CSV")
c, t, h, raw = doc.get("/examenes/plantilla")
plantilla = raw.decode("utf-8-sig")
ok(c == 200 and plantilla.startswith("Tipo;Pregunta;") and "Opción A" in plantilla, "descarga la plantilla")
c, t, *_ = doc.post(
    "/examenes/%s/importar" % qid, {}, {"archivo": ("preguntas.csv", plantilla.encode("cp1252", "replace"), "text/csv")}
)
ok(
    "Encontramos 6 preguntas" in t and "Lista desplegable" in t and "degrafilado" in t,
    "la plantilla (CSV de Excel) se lee completa",
)

print("== Excel (.xlsx)")
x = xlsx(
    [
        ["Pregunta", "Opción A", "Opción B", "Opción C", "Correcta", "Puntos"],
        ["¿Qué tela es más fresca?", "Algodón", "Poliéster", "Nylon", "A", "2"],
        ["¿Cuáles son fibras naturales?", "Lana", "Seda", "Acrílico", "A, B", "3"],
        ["La seda es de origen animal", "", "", "", "Verdadero", "1"],
    ]
)
c, t, *_ = doc.post(
    "/examenes/%s/importar" % qid,
    {},
    {"archivo": ("preguntas.xlsx", x, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
)
ok(
    "Encontramos 3 preguntas" in t and "Algodón" in t and "Casillas" in t and "Verdadero o falso" in t,
    "lee un Excel real (.xlsx)",
)

print("== Word (.docx)")
w = docx(
    [
        "Examen de costura",
        "¿Qué máquina se usa para remallar?",
        "a) Recta",
        "b) Remalladora *",
        "c) Collaretera",
        "¿El hilo de algodón encoge al lavarse?",
        "Respuesta: Verdadero",
    ]
)
c, t, *_ = doc.post(
    "/examenes/%s/importar" % qid,
    {},
    {"archivo": ("examen.docx", w, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
)
ok("Encontramos 2 preguntas" in t and "Remalladora" in t, "lee un Word (.docx), aunque no tenga números")

print("== Archivos malos")
c, t, *_ = doc.post("/examenes/%s/importar" % qid, {}, {"archivo": ("virus.exe", b"MZ...", "application/octet-stream")})
ok("Sube un archivo de Excel" in t, "rechaza otros tipos de archivo")
c, t, *_ = doc.post("/examenes/%s/importar" % qid, {}, {"archivo": ("roto.xlsx", b"no es un zip", "application/octet-stream")})
ok("No pudimos abrir el Excel" in t, "avisa si el Excel está dañado")
c, t, *_ = doc.post("/examenes/%s/importar" % qid, {"texto": ""})
ok("Pega el texto" in t, "pide texto o archivo")

print("== Permisos")
al = Cliente()
al.login("30000001", "30000001")
c, t, *_ = al.get("/examenes/%s/importar" % qid, seguir=False)
ok(c == 403, "un alumno no puede importar preguntas")

print()
print("FALLAS:", len(fallos))
for f in fallos:
    print(" -", f)
