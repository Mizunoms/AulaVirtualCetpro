"""Números para el inicio de administración y dirección. Las partes de asistencia y notas se llenan en la fase 4."""

from datetime import timedelta

from django.utils import timezone

# función() → {"pct", "registros", "sesiones", "desde"} de la semana
ASISTENCIA_SEMANA = []
# función() → list[dict(id, nombre, especialidad, docente, calificadas, pendientes, pct)]
NOTAS_POR_MODULO = []


def asistencia_semana():
    for f in ASISTENCIA_SEMANA:
        return f()
    lunes = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    return {"pct": None, "registros": 0, "sesiones": 0, "desde": lunes}


def notas_por_modulo():
    return [fila for f in NOTAS_POR_MODULO for fila in f()]


def notas_resumen(por_modulo):
    """Total de trabajos y tests calificados y pendientes, y el porcentaje al día."""
    calificadas = sum(m["calificadas"] for m in por_modulo)
    pendientes = sum(m["pendientes"] for m in por_modulo)
    total = calificadas + pendientes
    return {"calificadas": calificadas, "pendientes": pendientes, "pct": round(100 * calificadas / total) if total else None}
