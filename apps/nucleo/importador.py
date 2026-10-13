"""Convierte texto (por ejemplo, lo que escribe una IA), Excel, CSV o Word en preguntas de un formulario.
No guarda nada: devuelve las preguntas para que el docente las revise y confirme.

Formato de texto:
  1. ¿Pregunta?
  a) Opción
  b) Opción correcta *
  Respuesta: b            (también: «a, c» para varias; «Verdadero»/«Falso»; o el texto de una respuesta corta)
  Puntos: 2               (opcional)
  Explicación: ...        (opcional)

Formato de Excel / CSV (primera fila con títulos):
  Tipo | Pregunta | Opción A … Opción F | Correcta | Puntos | Obligatoria | Explicación

También lee tablas de Excel o CSV tal cual (`filas_tabla`), para cargar listas de alumnos.
El Excel y el Word se leen sin librerías: son archivos zip con XML por dentro.
"""

import csv
import html
import io
import re
import zipfile
from xml.etree.ElementTree import ParseError  # noqa: S405 - solo la clase de error; el XML se lee con defusedxml

from defusedxml import ElementTree as ET  # noqa: N817
from defusedxml.common import DefusedXmlException

MAX_PREGUNTAS = 100
MAX_BYTES_XML = 5 * 1024 * 1024
MAX_BYTES_TEXTO = 2_000_000

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_NS_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"

# Palabras que se aceptan en la columna «Tipo»
TIPOS = {
    "opciones": "opcion", "opcion": "opcion", "alternativas": "opcion", "varias opciones": "opcion", "una": "opcion",
    "casillas": "multiple", "multiple": "multiple", "varias": "multiple", "varias correctas": "multiple",
    "desplegable": "desplegable", "lista": "desplegable", "lista desplegable": "desplegable",
    "vf": "vf", "verdadero o falso": "vf", "verdadero falso": "vf", "v/f": "vf",
    "corta": "corta", "respuesta corta": "corta",
    "parrafo": "abierta", "abierta": "abierta", "respuesta larga": "abierta", "desarrollo": "abierta",
    "escala": "escala", "escala lineal": "escala",
    "fecha": "fecha", "hora": "hora",
    "archivo": "archivo", "subir archivo": "archivo", "foto": "archivo",
    "titulo": "seccion", "seccion": "seccion",
}  # fmt: skip

_SIN_TILDES = str.maketrans({"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"})

_NUMERADA = re.compile(r"^(?:pregunta\s*)?(\d{1,3})\s*[.):\-]\s*(.+)$", re.I)
_NUMERADA_ALGO = re.compile(r"^(?:pregunta\s*)?\d{1,3}\s*[.):\-]\s*\S", re.I)
_TERMINA_EN_PREGUNTA = re.compile(r"\?\s*:?$")
_ES_OPCION = re.compile(r"^([a-hA-H])\s*[).\-]\s*(.+)$")
_RESPUESTA = re.compile(r"^(?:respuesta(?:\s+correcta)?|correcta|clave)\s*[:\-]\s*(.+)$", re.I)
_PUNTOS = re.compile(r"^puntos?\s*[:\-]\s*([\d.,]+)", re.I)
_EXPLICACION = re.compile(r"^(?:explicaci[oó]n|justificaci[oó]n|retroalimentaci[oó]n)\s*[:\-]\s*(.+)$", re.I)
_MARCA_CORRECTA = re.compile(r"(\(\s*correct[ao]\s*\)|\*|✓|✔)\s*$", re.I)


class ImportadorError(Exception):
    """Mensaje listo para mostrar a la persona."""


def normalizar(texto):
    t = (texto or "").strip().lower().translate(_SIN_TILDES)
    return re.sub(r"\s+", " ", t).strip()


def _a_float(texto, defecto=0.0):
    try:
        return float(str(texto).replace(",", "."))
    except ValueError:
        return defecto


# ---------- Texto ----------


def _limpiar_linea(linea):
    linea = linea.replace(" ", " ").strip()
    linea = re.sub(r"^[#>\-•\s]+(?=\S)", "", linea)  # viñetas, títulos markdown
    linea = linea.replace("**", "").replace("__", "")  # negritas de markdown
    return linea.strip()


def _es_verdadero_falso(textos):
    return sorted(normalizar(t) for t in textos) == ["falso", "verdadero"]


def desde_texto(texto, es_examen):
    """Texto con las preguntas → {"preguntas": [...], "errores": [...]}"""
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Si nadie numeró las preguntas (p. ej. listas automáticas de Word), cada línea que termina en «?» es una pregunta.
    if not any(_NUMERADA_ALGO.match(_limpiar_linea(x)) for x in lineas):
        n = 0
        for i, x in enumerate(lineas):
            limpia = _limpiar_linea(x)
            if _TERMINA_EN_PREGUNTA.search(limpia) and not re.match(r"^[a-hA-H]\s*[).\-]", limpia):
                n += 1
                lineas[i] = f"{n}. {limpia}"

    bloques, actual = [], None
    for linea in lineas:
        limpia = _limpiar_linea(linea)
        if limpia == "":
            continue
        m = _NUMERADA.match(limpia)
        if m:  # nueva pregunta: «1. …», «1) …», «Pregunta 1: …»
            if actual:
                bloques.append(actual)
            actual = {
                "enunciado": m.group(2).strip(),
                "opciones": [],
                "respuesta": None,
                "puntos": None,
                "explicacion": None,
                "linea": m.group(1),
            }
            continue
        if actual is None:
            continue  # texto antes de la primera pregunta (saludos de la IA, títulos…)
        if m := _RESPUESTA.match(limpia):
            actual["respuesta"] = m.group(1).strip()
        elif m := _PUNTOS.match(limpia):
            actual["puntos"] = _a_float(m.group(1))
        elif m := _EXPLICACION.match(limpia):
            actual["explicacion"] = m.group(1).strip()
        elif m := _ES_OPCION.match(limpia):
            opcion = m.group(2).strip()
            marcada = bool(_MARCA_CORRECTA.search(opcion))
            opcion = _MARCA_CORRECTA.sub("", opcion).strip()
            actual["opciones"].append((m.group(1).upper(), opcion, marcada))
        elif not actual["opciones"]:
            actual["enunciado"] += " " + limpia  # la pregunta sigue en otra línea
    if actual:
        bloques.append(actual)

    preguntas, errores = [], []
    for b in bloques[:MAX_PREGUNTAS]:
        letras_correctas = [o[0] for o in b["opciones"] if o[2]]
        opciones = [(o[0], o[1]) for o in b["opciones"]]
        tipo = "vf" if b["opciones"] and _es_verdadero_falso([o[1] for o in opciones]) else ""
        p, error = _armar(
            tipo, b["enunciado"], opciones, b["respuesta"] or "", letras_correctas, b["puntos"], True, b["explicacion"], es_examen
        )
        if error:
            errores.append(f"Pregunta {b['linea']}: {error}")
        else:
            preguntas.append(p)
    if not bloques:
        errores.append("No encontramos preguntas. Cada pregunta debe empezar con su número, por ejemplo: «1. ¿Qué es…?».")
    return {"preguntas": preguntas, "errores": errores}


# ---------- Archivos ----------


def desde_archivo(archivo, nombre, es_examen):
    """Lee un archivo subido (xlsx, csv, docx o txt). `archivo` es un objeto con `.read()`."""
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if ext == "xlsx":
        return _desde_filas(_filas_xlsx(archivo), es_examen)
    if ext == "csv":
        return _desde_filas(_filas_csv(archivo), es_examen)
    if ext == "docx":
        return desde_texto(_texto_docx(archivo), es_examen)
    if ext == "txt":
        return desde_texto(_a_utf8(archivo.read(MAX_BYTES_TEXTO)), es_examen)
    raise ImportadorError("Sube un archivo de Excel (.xlsx), CSV, Word (.docx) o de texto (.txt).")


def filas_tabla(archivo, nombre, max_filas=MAX_PREGUNTAS + 1):
    """Filas de una tabla de Excel (.xlsx) o CSV, tal cual (para cargar listas de alumnos)."""
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if ext == "xlsx":
        return _filas_xlsx(archivo, max_filas)
    if ext in ("csv", "txt"):
        return _filas_csv(archivo, max_filas)
    raise ImportadorError("Sube un archivo de Excel (.xlsx) o CSV.")


def _buscar_columna(cabecera, nombres):
    for i, c in enumerate(cabecera):
        if c in nombres:
            return i
    return None


def _desde_filas(filas, es_examen):
    """Filas de la plantilla de Excel/CSV → preguntas."""
    if not filas:
        return {"preguntas": [], "errores": ["El archivo está vacío."]}
    cab = [normalizar(str(c)) for c in filas[0]]
    c_tipo = _buscar_columna(cab, ["tipo"])
    c_preg = _buscar_columna(cab, ["pregunta", "enunciado"])
    c_corr = _buscar_columna(cab, ["correcta", "respuesta", "respuesta correcta", "clave"])
    c_pts = _buscar_columna(cab, ["puntos", "puntaje"])
    c_obl = _buscar_columna(cab, ["obligatoria"])
    c_exp = _buscar_columna(cab, ["explicacion", "justificacion"])
    c_ops = [i for i, c in enumerate(cab) if re.match(r"^(opcion|alternativa)\s*([a-h1-8])?$", c)]
    if c_preg is None:
        return {
            "preguntas": [],
            "errores": ["No encontramos la columna «Pregunta». Usa la plantilla (la primera fila debe tener los títulos)."],
        }
    preguntas, errores = [], []
    for n, fila in enumerate(filas[1 : MAX_PREGUNTAS + 1], start=1):

        def v(i, fila=fila):
            return "" if i is None else str(fila[i] if i < len(fila) else "").strip()

        if v(c_preg) == "":
            continue
        opciones = [(chr(65 + k), v(i)) for k, i in enumerate(c_ops) if v(i) != ""]
        tipo_txt = normalizar(v(c_tipo))
        tipo = "" if tipo_txt == "" else TIPOS.get(tipo_txt)
        if tipo is None:
            errores.append(f"Fila {n + 1}: no conocemos el tipo «{v(c_tipo)}».")
            continue
        obligatoria = normalizar(v(c_obl)) not in ("no", "n", "0")
        puntos = _a_float(v(c_pts)) if v(c_pts) != "" else None
        p, error = _armar(tipo, v(c_preg), opciones, v(c_corr), [], puntos, obligatoria, v(c_exp) or None, es_examen)
        if error:
            errores.append(f"Fila {n + 1}: {error}")
        else:
            preguntas.append(p)
    return {"preguntas": preguntas, "errores": errores}


def _armar(tipo, enunciado, opciones, respuesta, letras_marcadas, puntos, obligatoria, explicacion, es_examen):
    """Arma una pregunta con el mismo formato que usa `Pregunta.guardar`.
    `opciones` = [(letra, texto), …]; `respuesta`: «B», «A, C», «Verdadero», o un texto (respuesta corta).
    Devuelve (pregunta, error)."""
    enunciado = enunciado.strip()[:3000]
    if enunciado == "":
        return None, "falta el texto de la pregunta."
    respuesta = respuesta.strip()
    letras_resp = []
    if respuesta and re.fullmatch(r"[a-hA-H](\s*[,;y/]\s*[a-hA-H])*\s*", respuesta):
        letras_resp = [x.upper() for x in re.findall(r"[a-hA-H]", respuesta)]
    correctas = list(dict.fromkeys([*letras_marcadas, *letras_resp]))

    if tipo == "":  # si no dijeron el tipo, se deduce
        if opciones:
            tipo = "multiple" if len(correctas) > 1 else "opcion"
        elif normalizar(respuesta) in ("v", "f", "verdadero", "falso"):
            tipo = "vf"
        elif respuesta:
            tipo = "corta"
        else:
            tipo = "abierta"
    p = {
        "tipo": tipo,
        "enunciado": enunciado,
        "ayuda": None,
        "imagen_ruta": None,
        "obligatoria": 0 if tipo == "seccion" else int(obligatoria),
        "puntos": max(0, min(100, 1 if puntos is None else puntos)) if es_examen and tipo != "seccion" else 0,
        "aceptadas": None,
        "explicacion": explicacion[:2000] if es_examen and explicacion else None,
        "permite_otra": 0,
        "escala_min": None,
        "escala_max": None,
        "etiqueta_min": None,
        "etiqueta_max": None,
        "opciones": [],
    }
    if tipo in ("opcion", "multiple", "desplegable"):
        if len(opciones) < 2:
            return None, "necesita al menos 2 opciones."
        for letra, texto in opciones:
            p["opciones"].append([texto[:500], es_examen and letra in correctas, "opcion"])
        n = sum(1 for o in p["opciones"] if o[1])
        if es_examen and p["puntos"] > 0 and n == 0:
            return None, "no dice cuál es la respuesta correcta (escribe «Respuesta: b» o marca la opción con *)."
        if es_examen and p["puntos"] > 0 and tipo != "multiple" and n > 1:
            p["tipo"] = "multiple"  # tiene varias correctas: se convierte en casillas
    elif tipo == "vf":
        r = normalizar(respuesta)
        if (r == "" or re.fullmatch(r"[a-h]", r)) and opciones:  # vino como «a) Verdadero b) Falso» + «Respuesta: a» o con *
            r = ""
            for letra, texto in opciones:
                if letra in correctas:
                    r = normalizar(texto)
        verdadero = r in ("v", "verdadero", "true", "si")
        falso = r in ("f", "falso", "false", "no")
        if es_examen and p["puntos"] > 0 and not verdadero and not falso:
            return None, "en verdadero o falso, la respuesta debe ser «Verdadero» o «Falso»."
        p["opciones"] = [["Verdadero", es_examen and verdadero, "opcion"], ["Falso", es_examen and falso, "opcion"]]
    elif tipo == "corta":
        if es_examen and respuesta:
            p["aceptadas"] = "\n".join(x.strip() for x in re.split(r"[|;]", respuesta) if x.strip())[:2000]
    elif tipo == "escala":
        p["escala_min"], p["escala_max"] = 1, 5
    return p, None


# ---------- Lectores de archivos ----------


def _a_utf8(datos):
    if isinstance(datos, str):
        return datos
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return datos.decode("cp1252", errors="replace")


def _filas_csv(archivo, max_filas=MAX_PREGUNTAS + 1):
    contenido = _a_utf8(archivo.read(MAX_BYTES_TEXTO)).lstrip("﻿")
    primera = contenido.split("\n", 1)[0]
    sep = ";" if primera.count(";") >= primera.count(",") else ","
    filas = []
    for fila in csv.reader(io.StringIO(contenido), delimiter=sep):
        filas.append(fila)
        if len(filas) > max_filas:
            break
    return filas


def _leer_zip(z, nombre):
    try:
        info = z.getinfo(nombre)
    except KeyError:
        return None
    if info.file_size > MAX_BYTES_XML:
        raise ImportadorError(f"El archivo es demasiado grande. Usa como máximo {MAX_PREGUNTAS} preguntas.")
    return z.read(nombre)


def _xml(datos):
    """XML de un Excel o Word subido por una persona: se lee con defusedxml, que no acepta DTD ni entidades
    (así no hay ataques de entidades externas ni de expansión)."""
    if re.search(rb"<!DOCTYPE", datos, re.I):
        raise ImportadorError("El archivo no es válido.")
    try:
        return ET.fromstring(datos)
    except DefusedXmlException as ex:
        raise ImportadorError("El archivo no es válido.") from ex
    except ParseError as ex:
        raise ImportadorError("El archivo está dañado.") from ex


def _texto_nodo(nodo):
    return "".join(t.text or "" for t in nodo.iter() if t.tag.endswith("}t") or t.tag == "t")


def _indice_columna(letras):
    n = 0
    for ch in letras.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _abrir_zip(archivo, mensaje):
    try:
        return zipfile.ZipFile(io.BytesIO(archivo.read()))
    except zipfile.BadZipFile as ex:
        raise ImportadorError(mensaje) from ex


def _ruta_primera_hoja(z):
    wb, rels = _leer_zip(z, "xl/workbook.xml"), _leer_zip(z, "xl/_rels/workbook.xml.rels")
    if wb is not None and rels is not None:
        hojas = _xml(wb).find(f"{_NS}sheets")
        primera = hojas.find(f"{_NS}sheet") if hojas is not None else None
        if primera is not None:
            rid = primera.get(f"{_NS_REL}id")
            for rel in _xml(rels).iter(f"{_NS_PKG}Relationship"):
                if rel.get("Id") == rid:
                    destino = (rel.get("Target") or "").lstrip("/")
                    return destino if destino.startswith("xl/") else "xl/" + destino
    return "xl/worksheets/sheet1.xml"


def _filas_xlsx(archivo, max_filas=MAX_PREGUNTAS + 1):
    """Lee la primera hoja de un .xlsx sin librerías (es un zip con XML)."""
    with _abrir_zip(archivo, "No pudimos abrir el Excel. Guárdalo otra vez como «Libro de Excel (.xlsx)».") as z:
        compartidas = []
        xml_ss = _leer_zip(z, "xl/sharedStrings.xml")
        if xml_ss is not None:
            compartidas = [_texto_nodo(si) for si in _xml(xml_ss).findall(f"{_NS}si")]
        xml_hoja = _leer_zip(z, _ruta_primera_hoja(z))
        if xml_hoja is None:
            raise ImportadorError("El Excel no tiene hojas con datos.")
        datos = _xml(xml_hoja).find(f"{_NS}sheetData")
        filas = []
        for row in datos.findall(f"{_NS}row") if datos is not None else []:
            fila = {}
            for c in row.findall(f"{_NS}c"):
                letras = re.sub(r"\d+", "", c.get("r") or "A") or "A"
                tipo = c.get("t") or ""
                v = c.find(f"{_NS}v")
                if tipo == "s":
                    pos = int(v.text) if v is not None and (v.text or "").isdigit() else -1
                    valor = compartidas[pos] if 0 <= pos < len(compartidas) else ""
                elif tipo == "inlineStr":
                    inline = c.find(f"{_NS}is")
                    valor = _texto_nodo(inline) if inline is not None else ""
                else:
                    valor = (v.text or "") if v is not None else ""
                fila[_indice_columna(letras)] = valor
            if fila:
                filas.append([fila.get(i, "") for i in range(max(fila) + 1)])
            if len(filas) > max_filas:
                break
        return filas


def _texto_docx(archivo):
    """Texto de un Word (.docx), un párrafo por línea."""
    with _abrir_zip(archivo, "No pudimos abrir el Word. Guárdalo otra vez como «Documento de Word (.docx)».") as z:
        datos = _leer_zip(z, "word/document.xml")
    if datos is None:
        raise ImportadorError("El Word está vacío o dañado.")
    xml = datos.decode("utf-8", errors="replace")
    xml = re.sub(r"<w:(?:tab|br)\s*/>", " ", xml)  # los saltos y tabulaciones, como espacios
    xml = xml.replace("</w:p>", "\n")  # cada párrafo en su línea
    # Las listas numeradas automáticas de Word no guardan el número; `desde_texto` lo resuelve con las líneas que terminan en «?».
    return html.unescape(re.sub(r"<[^>]+>", "", xml))
