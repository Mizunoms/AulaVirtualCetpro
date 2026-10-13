"""Cálculo de promedios y libro de notas del módulo.

- Cuentan las tareas con nota (0–20 o rúbrica). «Aprobó / No aprobó» no entra al promedio.
- Exámenes: cuenta la mejor nota del alumno.
- Si la fecha ya pasó y el alumno no entregó / no dio el examen, cuenta como 0.
- Si entregó y todavía no tiene nota (o falta revisar), no cuenta aún.
- La nota final pondera tres partes (trabajos, tests y asistencia) según `Evaluacion` (lo elige el docente).
"""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.academico import contenido
from apps.academico.models import Evaluacion
from apps.nucleo.utils import nota_fmt

from .models import porcentajes


def redondear(valor, decimales=1):
    """Redondeo «escolar» (0.25 → 0.3), no el del banquero."""
    return float(Decimal(str(valor)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP))


def nota_final(partes, pesos):
    """Nota final (0–20) a partir del promedio de cada parte. Las partes sin notas todavía no cuentan y su peso se reparte
    entre las demás. Devuelve None si aún no hay ninguna nota."""
    suma, peso_usado = 0.0, 0
    for parte, peso in (("tareas", pesos.peso_tareas), ("tests", pesos.peso_tests), ("asistencia", pesos.peso_asistencia)):
        if partes[parte] is not None and peso > 0:
            suma += partes[parte] * peso
            peso_usado += peso
    return redondear(suma / peso_usado, 1) if peso_usado else None


def valor_mostrar(act, est, vencida):
    """(valor para mostrar, valor que cuenta para el promedio o None)"""
    if act["tipo_calificacion"] == "aprobado":
        if est and est["aprobado"] is not None:
            texto = "Aprobó" if est["aprobado"] else "No aprobó"
        elif est:
            texto = "Por calificar"
        else:
            texto = "No entregó" if vencida else "—"
        return texto, None
    if est and est["nota"] is not None:
        return float(est["nota"]), float(est["nota"])
    if not est and vencida:
        return 0.0, 0.0
    if est:
        return ("Por revisar" if act["tipo"] == "examen" else "Por calificar"), None
    return "—", None


def partes_de(suma, asistencia):
    """Promedio de cada parte (0–20). La asistencia solo cuenta cuando ya hay alguna nota de trabajos o tests."""
    tareas = redondear(suma["tarea"][0] / suma["tarea"][1], 1) if suma["tarea"][1] else None
    tests = redondear(suma["examen"][0] / suma["examen"][1], 1) if suma["examen"][1] else None
    asis = (
        redondear(asistencia["pct"] * 20 / 100, 1)
        if (tareas is not None or tests is not None) and asistencia and asistencia["total"] > 0
        else None
    )
    return {"tareas": tareas, "tests": tests, "asistencia": asis}


def libro(modulo):
    """Libro de notas del módulo: actividades, pesos y, por alumno, `notas`, `partes`, `asistencia` y `promedio`."""
    actividades = contenido.actividades_con_nota(modulo)
    alumnos = list(modulo.alumnos())
    estados = contenido.estados_de_actividades(modulo)
    asis = porcentajes(modulo)
    pesos = Evaluacion.de(modulo)
    minima = float(pesos.nota_minima)
    ahora = timezone.now()
    for a in alumnos:
        a.notas = {}
        suma = {"tarea": [0.0, 0], "examen": [0.0, 0]}
        for act in actividades:
            mostrar, cuenta = valor_mostrar(act, estados.get(a.pk, {}).get(act["clave"]), act["fecha_limite"] < ahora)
            a.notas[act["clave"]] = mostrar
            if cuenta is not None:
                suma[act["tipo"]][0] += cuenta
                suma[act["tipo"]][1] += 1
        a.asistencia = asis.get(a.pk)
        a.partes = partes_de(suma, a.asistencia)
        a.promedio = nota_final(a.partes, pesos)
        a.celdas = [
            {"act": act, "valor": v, "num": isinstance(v, float), "bajo": isinstance(v, float) and v < minima}
            for act in actividades
            for v in [a.notas[act["clave"]]]
        ]
        a.situacion = "" if a.promedio is None else ("Aprobado" if a.promedio >= minima else "Desaprobado")
        a.bajo = a.promedio is not None and a.promedio < minima
    return {"actividades": actividades, "alumnos": alumnos, "pesos": pesos, "minima": minima}


def del_alumno(modulo, alumno):
    """Notas de un alumno en un módulo (tareas y exámenes), con promedio: `filas` (boletín), `partes`, `pesos`, `promedio`."""
    estados = contenido.estados_de_actividades(modulo).get(alumno.pk, {})
    ahora = timezone.now()
    filas = []
    suma = {"tarea": [0.0, 0], "examen": [0.0, 0]}
    for act in reversed(contenido.actividades_con_nota(modulo)):
        if act["clase"].situacion == "proxima":
            continue  # la clase todavía no empieza: el alumno aún no la ve
        est = estados.get(act["clave"])
        mostrar, cuenta = valor_mostrar(act, est, act["fecha_limite"] < ahora)
        es_numero = isinstance(mostrar, float)
        if es_numero:
            estado = "calificada" if est else "no_entrego"
        elif mostrar == "—":
            estado = "pendiente"
        elif mostrar in ("Por calificar", "Por revisar"):
            estado = "por_calificar"
        else:
            estado = "texto"
        filas.append(
            {
                "titulo": act["titulo"],
                "tipo": "Tarea" if act["tipo"] == "tarea" else ("Trabajo" if act["modo"] == "trabajo" else "Examen"),
                "fecha": act["fecha_limite"],
                "clase_titulo": act["clase"].titulo,
                "enlace": act["url"],
                "nota": mostrar if es_numero else None,
                "estado": estado,
                "texto": "" if es_numero else mostrar,
                "comentario": (est or {}).get("comentario"),
                "etiqueta_estado": "",
            }
        )
        if cuenta is not None:
            suma[act["tipo"]][0] += cuenta
            suma[act["tipo"]][1] += 1
    pesos = Evaluacion.de(modulo)
    partes = partes_de(suma, porcentajes(modulo).get(alumno.pk))
    filas.sort(key=lambda f: f["fecha"])
    return {"filas": filas, "partes": partes, "pesos": pesos, "promedio": nota_final(partes, pesos)}


def texto_celda(valor):
    """Una celda del libro: la nota sin decimales de más, o el texto («Por calificar», «—»…)."""
    return nota_fmt(valor) if isinstance(valor, float) else valor
