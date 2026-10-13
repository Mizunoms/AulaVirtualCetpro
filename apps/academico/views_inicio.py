"""Pantalla de inicio de cada rol: alumno, docente, administración y dirección."""

import calendar

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import Rol, Usuario
from apps.nucleo import menu
from apps.nucleo.models import Registro
from apps.nucleo.utils import MESES

from . import contenido, reportes
from .models import Aviso, Clase, Modulo
from .views import datos_de_modulo_alumno


def _calendario(dias_entrega):
    """Calendario del mes con los días que tienen algo por entregar: lista de semanas de 7 celdas (o None)."""
    hoy = timezone.localdate()
    primero = hoy.replace(day=1)
    huecos = primero.weekday()  # lunes = 0
    dias_mes = calendar.monthrange(hoy.year, hoy.month)[1]
    celdas = [None] * huecos
    for dia in range(1, dias_mes + 1):
        fecha = primero.replace(day=dia)
        cosas = dias_entrega.get(fecha.isoformat(), [])
        clases = " ".join(c for c in ("hoy" if fecha == hoy else "", "con-entrega" if cosas else "") if c)
        celdas.append({"dia": dia, "clases": clases, "cosas": cosas, "titulo": " · ".join(cosas)})
    while len(celdas) % 7:
        celdas.append(None)
    return {
        "mes": MESES[hoy.month],
        "anio": hoy.year,
        "semanas": [celdas[i : i + 7] for i in range(0, len(celdas), 7)],
        "dias_semana": [
            ("L", "lunes"),
            ("M", "martes"),
            ("M", "miércoles"),
            ("J", "jueves"),
            ("V", "viernes"),
            ("S", "sábado"),
            ("D", "domingo"),
        ],
    }


def contexto_alumno(request):
    u = request.user
    pendientes, grupos = contenido.pendientes_agrupados(u)
    modulos = list(Modulo.objects.con_alumnos().filter(matriculas__alumno=u, activo=True).order_by("nombre"))
    continuar = None
    vino = total = 0
    for m in modulos:
        m.datos = datos_de_modulo_alumno(m, u)
        a = m.datos["asistencia"]
        if a:
            vino += a["vino"]
            total += a["total"]
        actual = Clase.actual(list(m.clases.filter(visible=True)))
        if actual and actual.situacion == "abierta" and (continuar is None or m.datos["pendientes"] > continuar["pendientes"]):
            continuar = {"clase": actual, "modulo": m.nombre, "pendientes": m.datos["pendientes"]}
    dias = {}
    for p in pendientes:
        if p.limite:
            dias.setdefault(timezone.localtime(p.limite).date().isoformat(), []).append(p.titulo)
    return {
        "grupos": grupos,
        "grupos_lista": [
            ("vencida", "Ya pasó la fecha", "grupo-vencida", "alerta", "fecha-vencida", grupos["vencida"]),
            ("hoy", "Vence hoy", "grupo-hoy", "reloj", "fecha-hoy", grupos["hoy"]),
            ("proxima", "Próximas", "", "calendario", "fecha-proxima", grupos["proxima"]),
        ],
        "total": len(pendientes),
        "avisos": Aviso.de_alumno(u),
        "notas_nuevas": contenido.notas_nuevas(u),
        "mensajes_sin_leer": menu.contar("mensajes", u),
        "modulos": modulos,
        "continuar": continuar,
        "asistencia_global": round(100 * vino / total) if total else None,
        "calendario": _calendario(dias),
    }


def contexto_docente(request):
    u = request.user
    esperando = contenido.esperando_nota(u)
    por_modulo = {}
    for _url, modulo_id in esperando:
        por_modulo[modulo_id] = por_modulo.get(modulo_id, 0) + 1
    modulos = list(Modulo.objects.con_alumnos().filter(docente=u, activo=True).order_by("nombre"))
    for m in modulos:
        hoy = contenido.asistencia_hoy(m)
        m.asistencia_hoy = hoy["tomada_hoy"]
        m.registrados_hoy = hoy["registrados_hoy"]
        m.por_calificar = por_modulo.get(m.pk, 0)
        pct = round(100 * min(m.registrados_hoy, m.total_alumnos) / m.total_alumnos) if m.total_alumnos else 0
        completa = m.total_alumnos > 0 and m.registrados_hoy >= m.total_alumnos
        m.asist = {
            "completa": completa,
            "estado": "Pendiente" if m.registrados_hoy == 0 else ("Completa" if completa else "Incompleta"),
            "pct": pct,
        }
    total = len(esperando)
    ir_a_calificar = esperando[0][0] if total == 1 else menu.url_o_numeral("tareas:por_calificar")
    unico = modulos[0] if len(modulos) == 1 else None
    alumnos = sum(m.total_alumnos for m in modulos)
    mensajes = menu.contar("mensajes", u)
    kpis = [
        (reverse("academico:modulos"), len(modulos), "Módulo" if len(modulos) == 1 else "Módulos", "cursos", ""),
        (
            reverse("academico:alumnos", args=[unico.pk]) if unico else reverse("academico:modulos"),
            alumnos,
            "Alumno" if alumnos == 1 else "Alumnos",
            "usuarios",
            "",
        ),
        (ir_a_calificar, total, "Por calificar", "calificar", "kpi-alerta" if total else ""),
        (
            menu.url_o_numeral("mensajes:index"),
            mensajes,
            "Mensaje nuevo" if mensajes == 1 else "Mensajes nuevos",
            "mensaje",
            "kpi-aviso" if mensajes else "",
        ),
    ]
    return {
        "modulos": modulos,
        "por_calificar": total,
        "ir_a_calificar": ir_a_calificar,
        "proximas": contenido.proximas_de_docente(u),
        "mensajes_sin_leer": mensajes,
        "kpis": kpis,
        "primer_modulo": modulos[0] if modulos else None,
    }


def contexto_admin(request):
    u = request.user
    es_admin = u.rol == Rol.ADMIN
    conteo = dict(Usuario.objects.filter(is_active=True).values_list("rol").annotate(n=Count("id")))
    modulos = list(Modulo.objects.con_alumnos().order_by("-activo", "especialidad", "nombre"))
    pendientes = Usuario.objects.filter(rol=Rol.ALUMNO, is_active=True, password__startswith="!").count()
    por_modulo = reportes.notas_por_modulo()
    activos = sum(1 for m in modulos if m.activo)
    kpis = [
        (
            menu.url_o_numeral("cuentas:admin_personas") + "?rol=docente" if es_admin else reverse("academico:modulos"),
            conteo.get(Rol.DOCENTE, 0),
            "Docentes",
            "cuenta",
            "",
        ),
        (
            menu.url_o_numeral("cuentas:admin_personas") + "?rol=alumno" if es_admin else reverse("academico:modulos"),
            conteo.get(Rol.ALUMNO, 0),
            "Alumnos",
            "usuarios",
            "",
        ),
        (
            reverse("academico:admin_modulos") if es_admin else reverse("academico:modulos"),
            activos,
            "Módulos activos",
            "cursos",
            "",
        ),
        (
            menu.url_o_numeral("cuentas:admin_personas") + "?rol=pendientes" if es_admin else reverse("academico:modulos"),
            pendientes,
            "Sin contraseña aún",
            "clave",
            "kpi-alerta" if pendientes else "",
        ),
    ]
    return {
        "es_admin": es_admin,
        "kpis": kpis,
        "modulos": modulos,
        "asistencia": reportes.asistencia_semana(),
        "notas_modulos": por_modulo,
        "notas": reportes.notas_resumen(por_modulo),
        "periodos": Modulo.periodos(),
        "accesos": list(Registro.objects.filter(accion="acceso").select_related("usuario")[:6]) if es_admin else [],
        "movimientos": list(Registro.objects.exclude(accion="acceso").select_related("usuario")[:8]) if es_admin else [],
        "acciones": Registro.ACCIONES,
        "iconos_accion": {
            "acceso": "cuenta",
            "clave": "clave",
            "cuenta": "usuarios",
            "notas": "notas",
            "ajustes": "ajustes",
            "modulo": "cursos",
        },
    }


def inicio(request):
    """Devuelve (plantilla, contexto) según el rol."""
    rol = request.user.rol
    if rol == Rol.ALUMNO:
        return "inicio/alumno.html", contexto_alumno(request)
    if rol == Rol.DOCENTE:
        return "inicio/docente.html", contexto_docente(request)
    return "inicio/admin.html", contexto_admin(request)
