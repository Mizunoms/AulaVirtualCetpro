"""Lee el plan de estudios oficial (el Excel del Ministerio de Educación, hoja «Organización modular»):
el curso (programa de estudios), sus módulos y las unidades didácticas de cada módulo con sus créditos y horas.
El Excel se lee sin librerías (es un zip con XML), con `apps.nucleo.importador.LibroXlsx`."""

import re

from apps.nucleo import importador
from apps.nucleo.importador import ImportadorError, LibroXlsx

from .models import UnidadDidactica

MAX_MODULOS = 6
MAX_BYTES_XML = 10_000_000  # tope por parte del zip; el libro entero, 3 veces esto
HORAS_CREDITO_TEORICO = 16
HORAS_CREDITO_PRACTICO = 32
FILAS_DE_TITULOS = 40  # los títulos de la tabla están en las primeras filas


def norm(texto):
    """Minúsculas, sin tildes, «_» y saltos de línea como espacios (para comparar títulos)."""
    return re.sub(r"\s+", " ", importador.normalizar((texto or "").replace("_", " "))).strip()


def numero(texto):
    t = (texto or "").strip().replace(",", ".")
    try:
        return max(0.0, float(t))
    except ValueError:
        return 0.0


def oracion(texto):
    """«ATENCIÓN DE INCIDENTES» → «Atención de incidentes» (solo si todo está en mayúsculas)."""
    t = re.sub(r"\s+", " ", texto or "").strip()
    if t and t.upper() == t:
        t = t[:1].upper() + t[1:].lower()
    return t


def _buscar_hoja(hojas, palabras):
    """La ruta de la hoja cuyo nombre contiene todas las palabras (sin tildes)."""
    for nombre, ruta in hojas.items():
        n = norm(nombre)
        if all(p in n for p in palabras):
            return ruta
    return None


def leer(archivo):
    """Archivo subido → {"curso": nombre, "modulos": [...], "avisos": [...]}. Lanza `ImportadorError` con un mensaje para la persona."""
    with LibroXlsx(archivo, MAX_BYTES_XML) as libro:
        hojas = libro.hojas()
        ruta = _buscar_hoja(hojas, ["organizacion", "modular"])
        if ruta is None:
            raise ImportadorError(
                "No encontré la hoja «Organización modular». Sube el Excel del plan de estudios del Ministerio "
                "(el que tiene las hojas Programa de estudio, Organización modular, M1, M2…)."
            )
        filas = libro.filas(ruta)
        curso = _curso(filas)
        if curso == "":
            ruta_programa = _buscar_hoja(hojas, ["programa", "estudio"])
            curso = _curso(libro.filas(ruta_programa)) if ruta_programa else ""
    modulos, avisos = _modulos(filas)
    if not modulos:
        raise ImportadorError(
            "No encontré módulos con unidades didácticas en la hoja «Organización modular». "
            "Revisa que el archivo sea el plan de estudios completo."
        )
    return {"curso": curso, "modulos": modulos, "avisos": avisos}


def _curso(filas):
    """El nombre del programa de estudios: la celda que sigue al título «Denominación del programa de estudios»."""
    for n, fila in filas.items():
        if n > FILAS_DE_TITULOS:
            break
        for i, valor in fila.items():
            if norm(valor).startswith("denominacion del programa de estudios"):
                for j, otro in fila.items():
                    if j > i and otro.strip():
                        return otro.strip()[:100]
    return ""


def _columnas(filas):
    """(fila de títulos, columnas) según los títulos de la tabla; si no se encuentran, las del formato oficial."""
    c = {"modulo": 0, "unidad": 5, "teorico": 7, "practico": 8, "total": 9}
    for n, fila in filas.items():
        if n > FILAS_DE_TITULOS:
            break
        textos = {i: norm(t) for i, t in fila.items()}
        i_modulo = next((i for i, t in textos.items() if t == "modulo"), None)
        i_unidad = None
        for i, t in textos.items():
            if t.startswith("unidad didactica"):
                i_unidad = i
        if i_modulo is not None and i_unidad is not None:
            c["modulo"], c["unidad"] = i_modulo, i_unidad
            for i, t in textos.items():
                if t.startswith("credito teorico"):
                    c["teorico"] = i
                elif t.startswith("credito practico"):
                    c["practico"] = i
                elif t.startswith(("t.creditos", "total creditos")) or t == "creditos":
                    c["total"] = i
            return n, c
    return None, c


def _modulos(filas):
    """Los módulos con sus unidades, a partir de las filas de la hoja «Organización modular»: (lista, avisos)."""
    cabecera, c = _columnas(filas)
    if cabecera is None:
        return [], []
    modulos, actual, avisos = [], None, []
    for n, fila in filas.items():
        if n <= cabecera:
            continue
        m = fila.get(c["modulo"], "").strip()
        if m and norm(m).startswith("orientaciones"):
            break
        if m:
            modulos.append({"nombre": oracion(m), "unidades": [], "sobran": 0})
            actual = modulos[-1]
        if actual is None:
            continue
        nombre = re.sub(r"\s+", " ", fila.get(c["unidad"], "")).strip()
        if nombre == "":
            # La práctica en situaciones reales de trabajo (EFSRT) no es una unidad didáctica pero también suma créditos y horas.
            if not norm(fila.get(1, "")).startswith("experiencias formativas en situaciones reales"):
                continue
            nombre = "Experiencias formativas en situaciones reales de trabajo (EFSRT)"
        teorico = numero(fila.get(c["teorico"], ""))
        total = numero(fila.get(c["total"], ""))
        if total <= 0:
            total = teorico + numero(fila.get(c["practico"], ""))
        if total <= 0:
            continue  # fila vacía de la plantilla
        practico = max(0.0, total - teorico)
        if len(actual["unidades"]) >= UnidadDidactica.MAX:
            actual["sobran"] += 1
            continue
        actual["unidades"].append(
            {
                "nombre": nombre[:150],
                "creditos": _redondear(total),
                "horas": _redondear(teorico * HORAS_CREDITO_TEORICO + practico * HORAS_CREDITO_PRACTICO),
            }
        )
    lista = []
    for m in modulos:
        if not m["unidades"] or len(lista) >= MAX_MODULOS:
            continue  # los bloques vacíos de la plantilla no cuentan
        numero_modulo = len(lista) + 1
        if m["sobran"] > 0:
            avisos.append(
                f"El módulo {numero_modulo} tiene más de {UnidadDidactica.MAX} unidades: solo se tomaron las primeras {UnidadDidactica.MAX}."
            )
        lista.append(
            {
                "modulo": f"Módulo {numero_modulo}",
                "nombre": m["nombre"][:150],
                "unidades": m["unidades"],
                "creditos": sum(u["creditos"] for u in m["unidades"]),
                "horas": sum(u["horas"] for u in m["unidades"]),
            }
        )
    return lista, avisos


def _redondear(valor):
    """Redondeo «escolar» como el de PHP (2.5 → 3)."""
    return int(valor + 0.5)
