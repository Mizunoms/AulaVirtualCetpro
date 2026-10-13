"""Asistencia, notas del módulo, Excel/impresión y el registro consolidado."""

import csv
import re
import unicodedata
from datetime import date

from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.academico.models import Evaluacion, Modulo
from apps.academico.views import cargar_modulo, datos_de_modulo_alumno, modulo_del_docente
from apps.cuentas.models import Rol
from apps.nucleo import ajustes
from apps.nucleo.models import Registro
from apps.nucleo.permisos import exigir, prohibido
from apps.nucleo.utils import csv_fila, fecha_corta, nota_fmt, ok, plural, por_metodo, vista, volver_con_error

from . import calificacion
from .models import Asistencia, Estado, SesionAsistencia, historial_alumno, porcentajes, sesiones_recientes

# ===================================================================== Asistencia


def _fecha_valida(texto):
    try:
        return date.fromisoformat(texto) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto or "") else None
    except ValueError:
        return None


@exigir()
def asistencia(request, id):
    m, acceso = cargar_modulo(request, id)
    pagina = {"sub": m.nombre, "volver": reverse("academico:modulo", args=[id]), "menu": "cursos"}
    if request.GET.get("desde") == "inicio":
        pagina.update(volver=reverse("nucleo:inicio"), menu="inicio")
    if acceso == "alumno":
        return vista(
            request,
            "asistencia/alumno.html",
            {"resumen": porcentajes(m).get(request.user.pk), "historial": historial_alumno(m, request.user)},
            titulo="Mi asistencia",
            **pagina,
        )
    hoy = timezone.localdate()
    fecha = _fecha_valida(request.GET.get("fecha", "")) or hoy
    sesion = SesionAsistencia.objects.filter(modulo=m, fecha=fecha).first()
    estados = {a.alumno_id: a.estado for a in sesion.asistencias.all()} if sesion else {}
    alumnos = list(m.alumnos())
    for a in alumnos:
        a.estado_dia = estados.get(a.pk)
        a.estado_inicial = estados.get(a.pk, "presente")
    tema = sesion.tema if sesion else request.GET.get("tema", "")[:200]
    return vista(
        request,
        "asistencia/docente.html",
        {
            "modulo": m,
            "solo_lectura": acceso != "docente",
            "fecha": fecha.isoformat(),
            "hoy": hoy.isoformat(),
            "sesion": sesion,
            "alumnos": alumnos,
            "estados": Estado.choices,
            "anteriores": sesiones_recientes(m),
            "desde": "inicio" if request.GET.get("desde") == "inicio" else "",
            "tema": tema,
        },
        titulo="Asistencia de hoy" if fecha == hoy else f"Asistencia del {fecha_corta(fecha)}",
        **pagina,
    )


@require_POST
@exigir(Rol.DOCENTE)
def asistencia_guardar(request, id):
    yo = request.user
    m = modulo_del_docente(request, id)
    fecha = _fecha_valida(request.POST.get("fecha", "").strip())
    if fecha is None or fecha > timezone.localdate():
        return volver_con_error(
            request, reverse("evaluacion:asistencia", args=[id]), "Elige una fecha válida (hoy o un día anterior)."
        )
    permitidos = set(Estado.values)
    estados, faltaron = {}, 0
    for a in m.alumnos():
        v = request.POST.get(f"estado[{a.pk}]", "presente")
        estados[a.pk] = v if v in permitidos else "presente"
        faltaron += estados[a.pk] == Estado.FALTA
    sesion, _creada = SesionAsistencia.objects.update_or_create(
        modulo=m, fecha=fecha, defaults={"tema": request.POST.get("tema", "").strip()[:200]}
    )
    for alumno_id, estado in estados.items():
        Asistencia.objects.update_or_create(sesion=sesion, alumno_id=alumno_id, defaults={"estado": estado})
    Registro.anotar(
        yo, "notas", f"El docente {yo.nombre_completo} tomó la asistencia de {m.nombre} ({fecha.isoformat()}).", request
    )
    ok(request, "Asistencia guardada. " + (f"Faltaron {faltaron}." if faltaron else "Vinieron todos."))
    return redirect(reverse("nucleo:inicio") if request.POST.get("desde") == "inicio" else reverse("academico:modulo", args=[id]))


# ===================================================================== Notas


def _resumen_alumno(modulo, alumno):
    """Todo lo que el alumno ve de un módulo en sus notas: nota final, avance, asistencia y sus actividades."""
    datos = datos_de_modulo_alumno(modulo, alumno)
    return {
        "modulo": modulo,
        "datos": datos,
        "asistencia": porcentajes(modulo).get(alumno.pk),
        **calificacion.del_alumno(modulo, alumno),
    }


def _preparar_boletin(resumen):
    """Datos listos para la plantilla de «Mis notas» (aprueba, recientes, partes)."""
    minima = float(resumen["pesos"].nota_minima)
    prom = resumen["promedio"]
    resumen["minima"] = minima
    resumen["aprueba"] = prom is not None and prom >= minima
    resumen["recientes"] = [f for f in reversed(resumen["filas"]) if f["estado"] in ("calificada", "texto")][:3]
    resumen["chips_partes"] = [
        (texto, getattr(resumen["pesos"], peso), resumen["partes"][parte])
        for parte, texto, peso in (
            ("tareas", "Trabajos", "peso_tareas"),
            ("tests", "Tests", "peso_tests"),
            ("asistencia", "Asistencia", "peso_asistencia"),
        )
        if getattr(resumen["pesos"], peso) != 0
    ]
    for f in resumen["filas"]:
        f["bajo"] = f["nota"] is not None and f["nota"] < minima
        f["chip_estado"] = {
            "pendiente": ("chip-gris", "Por entregar" if f["tipo"] == "Tarea" else "Por responder"),
            "por_calificar": ("chip-gris", "Pendiente de calificación"),
        }.get(f["estado"])
    return resumen


@exigir(Rol.ALUMNO)
def mis_notas(request):
    """Mis notas (alumno): todas sus notas, por módulo."""
    u = request.user
    modulos = Modulo.objects.con_alumnos().filter(matriculas__alumno=u, activo=True).order_by("nombre")
    cursos = [_preparar_boletin(_resumen_alumno(m, u)) for m in modulos]
    return vista(
        request, "notas/alumno.html", {"cursos": cursos, "unico": None}, titulo="Mis notas", sub=u.nombre_completo, menu="notas"
    )


@exigir()
def notas_modulo(request, id):
    """Notas de un módulo: el alumno ve las suyas; el docente / dirección ve el libro de notas."""
    m, acceso = cargar_modulo(request, id)
    pagina = {
        "sub": m.nombre,
        "volver": reverse("academico:modulo", args=[id]),
        "menu": "notas" if acceso == "alumno" else "cursos",
    }
    if acceso == "alumno":
        cursos = [_preparar_boletin(_resumen_alumno(m, request.user))]
        return vista(request, "notas/alumno.html", {"cursos": cursos, "unico": m, "acceso": acceso}, titulo="Mis notas", **pagina)
    libro = calificacion.libro(m)
    return vista(
        request,
        "notas/docente.html",
        {
            "modulo": m,
            "acceso": acceso,
            "libro": libro,
            "minima": float(libro["pesos"].nota_minima),
            "puede_editar": acceso == "docente",
            "p": libro["pesos"],
            "campos_pesos": [
                ("peso_tareas", "Trabajos (foto o archivo) %", libro["pesos"].peso_tareas),
                ("peso_tests", "Tests y formularios %", libro["pesos"].peso_tests),
                ("peso_asistencia", "Asistencia %", libro["pesos"].peso_asistencia),
                ("nota_minima", "Se aprueba con", nota_fmt(libro["pesos"].nota_minima)),
            ],
        },
        titulo="Notas y reportes",
        **pagina,
    )


@require_POST
@exigir(Rol.DOCENTE)
def notas_pesos(request, id):
    """El docente elige cuánto pesa cada parte de la nota final y con cuánto se aprueba."""
    m = modulo_del_docente(request, id)
    volver = reverse("evaluacion:notas_modulo", args=[id]) + "#pesos"

    def entero(clave):
        try:
            return int(request.POST.get(clave, "-1"))
        except ValueError:
            return -1

    t, q, a = entero("peso_tareas"), entero("peso_tests"), entero("peso_asistencia")
    try:
        minima = float(request.POST.get("nota_minima", "11").strip().replace(",", "."))
    except ValueError:
        minima = -1
    if min(t, q, a) < 0 or t + q + a != 100:
        return volver_con_error(request, volver, f"Los tres porcentajes deben sumar 100. Ahora suman {max(0, t + q + a)}.")
    if minima < 0 or minima > 20:
        return volver_con_error(request, volver, "La nota para aprobar debe estar entre 0 y 20.")
    Evaluacion.objects.update_or_create(
        modulo=m, defaults={"peso_tareas": t, "peso_tests": q, "peso_asistencia": a, "nota_minima": round(minima, 2)}
    )
    ok(request, f"Listo: la nota final se calcula con trabajos {t}%, tests {q}% y asistencia {a}%.")
    return redirect(reverse("evaluacion:notas_modulo", args=[id]))


def _respuesta_csv(nombre):
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    respuesta["X-Content-Type-Options"] = "nosniff"
    respuesta.write("﻿")  # marca para que Excel reconozca las tildes
    return respuesta


def _num(valor):
    return nota_fmt(valor).replace(".", ",") if valor is not None else ""


@exigir()
def notas_excel(request, id):
    """Descarga para Excel (CSV en UTF-8, separado por punto y coma, como lo abre Excel en español)."""
    m, acceso = cargar_modulo(request, id)
    if acceso == "alumno":
        return prohibido(request)
    libro = calificacion.libro(m)
    p = libro["pesos"]
    ascii_ = unicodedata.normalize("NFKD", m.nombre).encode("ascii", "ignore").decode().lower()
    respuesta = _respuesta_csv(
        f"notas-{re.sub(r'[^a-z0-9]+', '-', ascii_).strip('-') or 'curso'}-{timezone.localdate().isoformat()}.csv"
    )
    w = csv.writer(respuesta, delimiter=";")
    hoy = timezone.localdate().strftime("%d/%m/%Y")
    w.writerow([f"{ajustes.ajuste('centro_nombre')} - {m.nombre}"])
    w.writerow([f"Docente: {m.docente.nombre_completo}", f"Periodo: {m.periodo}", f"Turno: {m.turno}", f"Fecha: {hoy}"])
    w.writerow([])
    cabecera = ["N°", "DNI", "Apellidos", "Nombres"] + [act["etiqueta"] + act["titulo"] for act in libro["actividades"]]
    cabecera += [
        f"Trabajos ({p.peso_tareas}%)",
        f"Tests ({p.peso_tests}%)",
        f"Asistencia ({p.peso_asistencia}%)",
        "Nota final",
        "Asistencia %",
        "Situación",
    ]
    w.writerow(csv_fila(cabecera))
    for i, a in enumerate(libro["alumnos"], start=1):
        fila = [i, a.dni or "", a.apellidos, a.nombres]
        fila += [_num(c["valor"]) if c["num"] else c["valor"] for c in a.celdas]
        fila += [_num(a.partes[x]) for x in ("tareas", "tests", "asistencia")]
        fila += [_num(a.promedio), a.asistencia["pct"] if a.asistencia else "", a.situacion]
        w.writerow(csv_fila(fila))
    return respuesta


@exigir()
def notas_imprimir(request, id):
    """Versión para imprimir o guardar como PDF desde el navegador."""
    from django.shortcuts import render

    m, acceso = cargar_modulo(request, id)
    if acceso == "alumno":
        return prohibido(request)
    libro = calificacion.libro(m)
    return render(
        request,
        "notas/imprimir.html",
        {"modulo": m, "libro": libro, "minima": float(libro["pesos"].nota_minima), "hoy": timezone.localdate()},
    )


# ===================================================================== Reporte consolidado


@exigir(Rol.ADMIN, Rol.DIRECCION)
def consolidado(request):
    """Registro consolidado (Excel): todos los alumnos de los módulos activos con su asistencia y nota final."""
    u = request.user
    periodo = request.GET.get("periodo", "")
    periodo = periodo if periodo in Modulo.periodos() else ""
    filas = []
    for m in Modulo.objects.activos().select_related("docente").order_by("especialidad", "nombre"):
        if periodo and m.periodo != periodo:
            continue
        libro = calificacion.libro(m)
        minima = float(libro["pesos"].nota_minima)
        for a in libro["alumnos"]:
            nota = a.promedio
            filas.append(
                [
                    m.periodo, m.especialidad, m.nombre, m.turno, m.docente.nombre_completo, a.dni or "", a.apellidos, a.nombres,
                    f"{a.asistencia['pct']}%" if a.asistencia else "", nota_fmt(nota) if nota is not None else "",
                    "Sin nota" if nota is None else ("Aprobado" if nota >= minima else "Desaprobado"),
                ]
            )  # fmt: skip
    Registro.anotar(
        u,
        "notas",
        f"{u.nombre_completo} exportó el registro consolidado"
        + (f" del periodo {periodo}" if periodo else "")
        + f" ({plural(len(filas), 'fila', 'filas')}).",
        request,
    )
    respuesta = _respuesta_csv(f"registro-consolidado-{timezone.localdate().isoformat()}.csv")
    w = csv.writer(respuesta, delimiter=";")
    w.writerow([f"{ajustes.ajuste('centro_nombre')} - Registro consolidado"])
    w.writerow(
        [f"Fecha: {timezone.localdate().strftime('%d/%m/%Y')}", f"Periodo: {periodo}" if periodo else "Todos los módulos activos"]
    )
    w.writerow([])
    w.writerow(
        ["Periodo", "Curso", "Módulo", "Turno", "Docente", "DNI", "Apellidos", "Nombres", "Asistencia", "Nota final", "Condición"]
    )
    for f in filas:
        w.writerow(csv_fila(f))
    return respuesta


asistencia_o_guardar = por_metodo(GET=asistencia, POST=asistencia_guardar)
