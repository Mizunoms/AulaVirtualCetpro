"""Cómo se leen, corrigen y resumen las respuestas de un formulario.

Examen (corrección automática):
- Varias opciones, lista desplegable, verdadero o falso: puntaje completo si eligió la correcta.
- Casillas: puntaje completo solo si marcó exactamente las correctas.
- Respuesta corta: se compara sin mayúsculas, tildes ni espacios de más con las respuestas aceptadas.
- Párrafo, escala, fecha, hora, archivo y cuadrículas con puntos: los revisa el docente.
- Nota final (0–20) = puntaje obtenido / puntaje total × 20.
Trabajo: el docente lee todo y pone una nota. Encuesta: no lleva nota.
"""

import json
import random
import re
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count, F, Max, Q, Sum
from django.utils import timezone

from .models import CUADRICULAS, ELEGIR, TOLERANCIA_MIN, Intento, Respuesta

_SIN_TILDES = str.maketrans({"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"})


def redondear(valor, decimales=2):
    """Redondeo «escolar» (0.125 → 0.13), no el del banquero."""
    return float(Decimal(str(valor)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP))


def normalizar(texto):
    """Minúsculas, sin tildes, sin signos y con un solo espacio entre palabras (para comparar respuestas cortas)."""
    t = re.sub(r"\s+", " ", (texto or "").strip().lower().translate(_SIN_TILDES))  # tabulaciones y saltos, como espacios
    return "".join(c for c in t if c.isalnum() or c == " ").strip()


# ---------- Leer lo que respondió el alumno ----------

_CLAVE = re.compile(r"^(op|txt|otra|grid)\[(\d+)\](?:\[(\d+)\])?(\[\])?$")


def entrada_de_post(post):
    """Ordena el POST del formulario de respuestas (op[12], op[12][], txt[12], otra[12], grid[12][34], grid[12][34][]) en
    {"op": {12: [valores]}, "txt": {12: texto}, "otra": {12: texto}, "grid": {12: {34: [valores]}}}."""
    e = {"op": {}, "txt": {}, "otra": {}, "grid": {}}
    for clave in post:
        m = _CLAVE.match(clave)
        if not m:
            continue
        tipo, pid, fid = m.group(1), int(m.group(2)), m.group(3)
        valores = post.getlist(clave)
        if tipo == "op":
            e["op"].setdefault(pid, []).extend(valores)
        elif tipo == "grid" and fid is not None:
            e["grid"].setdefault(pid, {}).setdefault(int(fid), []).extend(valores)
        elif tipo in ("txt", "otra"):
            e[tipo][pid] = valores[-1] if valores else ""
    return e


def _enteros(valores):
    return [int(v) for v in valores if str(v).strip().isdigit()]


def leer(p, entrada, archivos=None):
    """Lo que respondió el alumno en una pregunta, ya limpio y validado:
    {"opciones": [ids], "otra", "otra_marcada", "texto", "grid": {fila_id: col_id | [col_id]}, "archivo": (ruta, nombre) o None}"""
    pid = p.pk
    validas = [o.pk for o in p.opciones]
    marcadas = list(entrada.get("op", {}).get(pid, []))
    otra_marcada = "otra" in marcadas and p.permite_otra
    marcadas = [m for m in _enteros(marcadas) if m in validas]
    if p.tipo in ("opcion", "desplegable", "vf") and len(marcadas) > 1:
        marcadas = marcadas[:1]
    otra = (entrada.get("otra", {}).get(pid) or "").strip()[:500] if otra_marcada else ""
    texto = (entrada.get("txt", {}).get(pid) or "").strip()[:5000]

    if p.tipo == "escala":
        try:
            n = int(texto)
        except ValueError:
            n = None
        desde = 1 if p.escala_min is None else p.escala_min
        hasta = 5 if p.escala_max is None else p.escala_max
        texto = str(n) if n is not None and desde <= n <= hasta else ""
    elif p.tipo == "fecha":
        try:
            texto = texto if datetime.strptime(texto, "%Y-%m-%d").strftime("%Y-%m-%d") == texto else ""
        except ValueError:
            texto = ""
    elif p.tipo == "hora":
        texto = texto if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", texto) else ""

    grid = {}
    if p.tipo in CUADRICULAS:
        filas = [f.pk for f in p.filas]
        cols = [c.pk for c in p.columnas]
        for fila_id, valor in entrada.get("grid", {}).get(pid, {}).items():
            if fila_id not in filas:
                continue
            elegidas = [c for c in _enteros(valor) if c in cols]
            if elegidas:
                grid[fila_id] = elegidas[0] if p.tipo == "cuadricula" else elegidas
    return {
        "opciones": marcadas,
        "otra": otra,
        "otra_marcada": otra_marcada,
        "texto": texto,
        "grid": grid,
        "archivo": (archivos or {}).get(pid),
    }


def vacia(p, r):
    if p.tipo == "seccion":
        return False
    if p.tipo in ELEGIR:
        return not r["opciones"] and r["otra"] == ""
    if p.tipo == "archivo":
        return r["archivo"] is None
    if p.tipo in CUADRICULAS:
        return len(r["grid"]) < len(p.filas)
    return r["texto"] == ""


def faltantes(preguntas, entrada, archivos=None):
    """Números de las preguntas obligatorias que quedaron sin responder."""
    faltan, n = [], 0
    for p in preguntas:
        if p.tipo == "seccion":
            continue
        n += 1
        if p.obligatoria and vacia(p, leer(p, entrada, archivos)):
            faltan.append(n)
    return faltan


# ---------- Corregir ----------


def _corregir(p, r, esta_vacia):
    """(puntos obtenidos, ¿falta que lo revise el docente?)"""
    pts = float(p.puntos)
    if pts <= 0 or esta_vacia:
        return 0.0, False
    correctas = sorted(o.pk for o in p.opciones if o.correcta)
    if p.tipo in ("opcion", "desplegable", "vf"):
        acierta = not r["otra_marcada"] and len(r["opciones"]) == 1 and r["opciones"][0] in correctas
        return (pts if acierta else 0.0), False
    if p.tipo == "multiple":
        acierta = not r["otra_marcada"] and sorted(r["opciones"]) == correctas
        return (pts if acierta else 0.0), False
    if p.tipo == "corta":
        aceptadas = [a for a in (normalizar(x) for x in p.respuestas_aceptadas.splitlines()) if a]
        if not aceptadas:
            return None, True  # sin respuesta modelo: la revisa el docente
        return (pts if normalizar(r["texto"]) in aceptadas else 0.0), False
    return None, True  # párrafo, escala, fecha, hora, archivo, cuadrículas


def nota_de(puntaje, maximo):
    """Nota de 0 a 20 según los puntos obtenidos."""
    return redondear(20 * puntaje / maximo, 2) if maximo > 0 else 0.0


@transaction.atomic
def entregar(intento, formulario, preguntas, entrada, archivos=None):
    """Corrige (si es examen), guarda las respuestas y cierra el intento. `archivos` = {pregunta_id: (ruta, nombre)} ya guardados."""
    puntaje = maximo = 0.0
    pendiente = False
    for p in preguntas:
        if p.tipo == "seccion":
            continue
        r = leer(p, entrada, archivos)
        esta_vacia = vacia(p, r)
        obtenido = None
        if formulario.modo == "examen":
            obtenido, revisar = _corregir(p, r, esta_vacia)
            maximo += float(p.puntos)
            if revisar:
                pendiente = True
            else:
                puntaje += obtenido
        texto = r["texto"]
        if r["grid"]:
            texto = json.dumps(r["grid"])
        elif r["otra"] != "":
            texto = r["otra"]
        ruta, nombre = r["archivo"] or ("", "")
        Respuesta.objects.update_or_create(
            intento=intento,
            pregunta=p,
            defaults={
                "opciones": ",".join(str(i) for i in r["opciones"]),
                "texto": texto,
                "archivo_ruta": ruta,
                "archivo_nombre": nombre,
                "puntos": None if obtenido is None else Decimal(str(round(obtenido, 2))),
            },
        )
    fin = intento.fin_de_tiempo
    ahora = timezone.now()
    tarde = ahora > fin + timedelta(minutes=TOLERANCIA_MIN)
    if formulario.modo == "examen":
        nota = None if pendiente else nota_de(puntaje, maximo)
        revisado, pje, pje_max = (not pendiente), redondear(puntaje), redondear(maximo)
    elif formulario.modo == "trabajo":
        nota, revisado, pje, pje_max = None, False, None, None
    else:  # encuesta: no lleva nota
        nota, revisado, pje, pje_max = None, True, None, None
    intento.fin = ahora
    intento.fuera_tiempo = tarde
    intento.puntaje = None if pje is None else Decimal(str(pje))
    intento.puntaje_max = None if pje_max is None else Decimal(str(pje_max))
    intento.nota = None if nota is None else Decimal(str(nota))
    intento.revisado = revisado
    intento.save()


@transaction.atomic
def revisar(intento, puntos, comentarios, general=""):
    """Examen: el docente pone los puntos de las preguntas que revisa él y se cierra la nota.
    `puntos` = {pregunta_id: Decimal}, `comentarios` = {pregunta_id: texto}."""
    for pid, pts in puntos.items():
        Respuesta.objects.filter(intento=intento, pregunta_id=pid).update(puntos=pts, comentario=comentarios.get(pid) or "")
    respuestas = Respuesta.objects.filter(intento=intento)
    suma = float(respuestas.aggregate(s=Sum("puntos"))["s"] or 0)
    faltan = respuestas.filter(puntos__isnull=True).exists()
    intento.puntaje = Decimal(str(redondear(suma)))
    intento.nota = None if faltan else Decimal(str(nota_de(suma, float(intento.puntaje_max or 0))))
    intento.revisado = not faltan
    intento.comentario = general or ""
    intento.save(update_fields=["puntaje", "nota", "revisado", "comentario"])


def calificar_trabajo(intento, nota, comentario=""):
    """Trabajo: el docente pone una nota de 0 a 20 y un comentario a todo el formulario."""
    intento.nota = Decimal(str(redondear(nota)))
    intento.revisado = True
    intento.comentario = comentario or ""
    intento.save(update_fields=["nota", "revisado", "comentario"])


def mezclar(lista, semilla):
    """Orden al azar pero siempre el mismo para un intento."""
    lista = list(lista)
    random.Random(semilla).shuffle(lista)
    return lista


# ---------- Resultados para el docente ----------


def terminados(formulario):
    return Intento.objects.filter(formulario=formulario, fin__isnull=False)


def resultados(formulario, modulo):
    """Por alumno del módulo: sus intentos, su mejor nota, el intento que se abre y cuántos faltan revisar."""
    por_alumno = {}
    for i in terminados(formulario):
        por_alumno.setdefault(i.alumno_id, []).append(i)
    filas = []
    for a in modulo.alumnos():
        mios = por_alumno.get(a.pk, [])
        notas = [float(i.nota) for i in mios if i.revisado and i.nota is not None]
        # el intento que se abre: primero los que faltan revisar; luego la mejor nota; luego el más reciente
        elegido = min(mios, key=lambda i: (i.revisado, -(float(i.nota) if i.nota is not None else -1), -i.pk)) if mios else None
        filas.append(
            {
                "alumno": a,
                "alumno_id": a.pk,
                "nombres": a.nombres,
                "apellidos": a.apellidos,
                "intentos": len(mios),
                "mejor_nota": max(notas) if notas else None,
                "intento_id": elegido.pk if elegido else None,
                "por_revisar": sum(1 for i in mios if not i.revisado),
            }
        )
    return filas


def aciertos_por_pregunta(formulario):
    """% de alumnos que acertaron cada pregunta (solo preguntas con puntos ya calificadas)."""
    consulta = (
        Respuesta.objects.filter(
            intento__formulario=formulario, intento__fin__isnull=False, puntos__isnull=False, pregunta__puntos__gt=0
        )
        .values("pregunta")
        .annotate(total=Count("id"), bien=Count("id", filter=Q(puntos__gte=F("pregunta__puntos"))))
    )
    return {f["pregunta"]: int(redondear(100 * f["bien"] / max(1, f["total"]), 0)) for f in consulta}


def _columnas_de(valor):
    return valor if isinstance(valor, list) else [valor]


def grid_de(respuesta):
    """La cuadrícula guardada de una respuesta: {fila_id: [col_id, …]}"""
    try:
        datos = json.loads(respuesta.texto) if respuesta and respuesta.texto else {}
    except ValueError:
        return {}
    return {int(f): [int(c) for c in _columnas_de(cols)] for f, cols in datos.items() if str(f).isdigit()}


def resumen(formulario, preguntas):
    """Resumen tipo «Respuestas» de Google Forms, por pregunta: {pregunta_id: {total, conteo, otras, textos, grid}}."""
    por_pregunta = {}
    todas = (
        Respuesta.objects.filter(intento__formulario=formulario, intento__fin__isnull=False)
        .select_related("intento__alumno")
        .order_by("-intento__fin", "id")
    )
    for r in todas:
        por_pregunta.setdefault(r.pregunta_id, []).append(r)
    res = {}
    for p in preguntas:
        s = {"total": 0, "conteo": {}, "otras": [], "textos": [], "grid": {}}
        for r in por_pregunta.get(p.pk, []):
            nombre = r.intento.alumno.nombre_completo
            if not r.tiene_algo:
                continue
            s["total"] += 1
            if p.tipo in ELEGIR:
                for oid in r.ids_marcados:
                    s["conteo"][oid] = s["conteo"].get(oid, 0) + 1
                if r.texto:
                    s["otras"].append((nombre, r.texto))
            elif p.tipo == "escala":
                if r.texto.isdigit():
                    s["conteo"][int(r.texto)] = s["conteo"].get(int(r.texto), 0) + 1
            elif p.tipo in CUADRICULAS:
                for fila, cols in grid_de(r).items():
                    for col in cols:
                        s["grid"].setdefault(fila, {})[col] = s["grid"].get(fila, {}).get(col, 0) + 1
            elif p.tipo == "archivo":
                s["textos"].append((nombre, r.archivo_nombre, r.pk))
            else:
                s["textos"].append((nombre, r.texto, r.pk))
        res[p.pk] = s
    return res


def texto_respuesta(p, r):
    """Texto legible de una respuesta (para la descarga a Excel)."""
    if r is None:
        return ""
    nombres = {o.pk: o.texto for o in [*p.opciones, *p.filas, *p.columnas]}
    partes = [nombres.get(oid, "") for oid in r.ids_marcados]
    if p.tipo in CUADRICULAS:
        for fila, cols in grid_de(r).items():
            partes.append(f"{nombres.get(fila, '')}: " + " / ".join(nombres.get(c, "") for c in cols))
    elif p.tipo == "archivo":
        partes.append(r.archivo_nombre)
    elif r.texto:
        partes.append(f"Otra: {r.texto}" if p.tipo in ELEGIR else r.texto)
    return "; ".join(x for x in partes if x)


def mejor_nota_del_alumno(formulario, alumno):
    return Intento.objects.filter(formulario=formulario, alumno=alumno, revisado=True).aggregate(m=Max("nota"))["m"]
