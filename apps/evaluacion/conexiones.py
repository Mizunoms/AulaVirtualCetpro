"""Cómo la asistencia y las notas se muestran en el inicio, el módulo y los reportes."""

from datetime import timedelta

from django.utils import timezone

from apps.academico import contenido, reportes, resumen
from apps.academico.models import Modulo
from apps.cuentas import resumen as resumen_cuentas

from . import calificacion
from .models import Asistencia, Estado, SesionAsistencia, porcentajes, registrados_hoy, tomada_hoy


def asistencia_hoy(modulo):
    return {"tomada_hoy": tomada_hoy(modulo), "registrados_hoy": registrados_hoy(modulo)}


def resumen_alumno(modulo, alumno, con_promedio=True):
    resultado = {"promedio": None, "asistencia": porcentajes(modulo).get(alumno.pk)}
    if con_promedio:
        resultado["promedio"] = calificacion.del_alumno(modulo, alumno)["promedio"]
    return resultado


def asistencia_semana():
    """Asistencia de todos los módulos activos desde el lunes de esta semana."""
    hoy = timezone.localdate()
    lunes = hoy - timedelta(days=hoy.weekday())
    consulta = Asistencia.objects.filter(sesion__modulo__activo=True, sesion__fecha__range=(lunes, hoy))
    total = consulta.count()
    vino = consulta.filter(estado__in=[Estado.PRESENTE, Estado.TARDE, Estado.JUSTIFICADA]).count()
    sesiones = consulta.values("sesion").distinct().count()
    pct = int(calificacion.redondear(100 * vino / total, 0)) if total else None
    return {"pct": pct, "registros": total, "sesiones": sesiones, "desde": lunes}


def notas_por_modulo():
    """Por módulo activo: trabajos y tests calificados y pendientes de calificar (los pendientes primero)."""
    filas = []
    for m in Modulo.objects.activos().select_related("docente"):
        calificadas, pendientes = contenido.calificacion_del_modulo(m)
        total = calificadas + pendientes
        filas.append(
            {
                "id": m.pk,
                "nombre": m.nombre,
                "especialidad": m.especialidad,
                "docente": m.docente.nombre_completo,
                "calificadas": calificadas,
                "pendientes": pendientes,
                "pct": int(calificacion.redondear(100 * calificadas / total, 0)) if total else None,
            }
        )
    filas.sort(key=lambda f: (-f["pendientes"], f["nombre"]))
    return filas


def conectar():
    contenido.ASISTENCIA_HOY.append(asistencia_hoy)
    contenido.RESUMEN_ALUMNO.append(resumen_alumno)
    contenido.ASISTENCIA_POR_ALUMNO.append(porcentajes)
    reportes.ASISTENCIA_SEMANA.append(asistencia_semana)
    reportes.NOTAS_POR_MODULO.append(notas_por_modulo)
    resumen.registrar_contador(
        "día de asistencia", "días de asistencia", lambda m: SesionAsistencia.objects.filter(modulo=m).count()
    )
    resumen.registrar_registros_de_alumnos(lambda m: Asistencia.objects.filter(sesion__modulo=m).exists())
    resumen_cuentas.registrar_contador(
        20, "registro de asistencia", "registros de asistencia", lambda u: Asistencia.objects.filter(alumno=u).count()
    )
