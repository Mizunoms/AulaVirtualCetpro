"""Copiar un módulo para el siguiente periodo: clases, materiales, tareas y formularios (con sus preguntas).

No copia alumnos, entregas, respuestas, notas, asistencia ni mensajes. Las fechas se corren para que la primera
clase empiece en la fecha elegida. Cada tipo de contenido registra cómo se copia con `registrar_copiador`.
"""

from datetime import date, datetime, timedelta

from django.db import transaction

from .models import Clase, Evaluacion, Modulo, UnidadDidactica

# función(clase_origen, clase_nueva, mover) para copiar lo que hay dentro de una clase
COPIADORES = []


def registrar_copiador(funcion):
    COPIADORES.append(funcion)
    return funcion


def _corrimiento(origen, clases, desde):
    """Cuántos días hay que correr las fechas para que la primera clase empiece en `desde` (0 si no se eligió)."""
    if desde is None:
        return 0
    inicios = [c.fecha_inicio for c in clases if c.fecha_inicio is not None]
    primera = min(inicios) if inicios else None
    if primera is None:
        from apps.tareas.models import Tarea

        fechas = [t.fecha_limite.date() for t in Tarea.objects.filter(clase__modulo=origen)]
        primera = min(fechas) if fechas else None
    return (desde - primera).days if primera else 0


@transaction.atomic
def copiar_modulo(origen, docente, nombre, periodo, desde):
    nuevo = Modulo.crear(
        nombre=nombre,
        especialidad=origen.especialidad,
        modulo=origen.modulo,
        periodo=periodo,
        turno=origen.turno,
        horario=origen.horario,
        docente=docente,
    )
    UnidadDidactica.copiar(origen, nuevo)
    try:
        ev = origen.evaluacion
        Evaluacion.objects.create(
            modulo=nuevo,
            peso_tareas=ev.peso_tareas,
            peso_tests=ev.peso_tests,
            peso_asistencia=ev.peso_asistencia,
            nota_minima=ev.nota_minima,
        )
    except Evaluacion.DoesNotExist:
        pass

    clases = list(origen.clases.all())
    dias = _corrimiento(origen, clases, desde)
    delta = timedelta(days=dias)

    def mover(f):
        if f is None:
            return None
        if isinstance(f, datetime):
            return f + delta
        return f + delta if isinstance(f, date) else f

    for c in clases:
        copia = Clase.objects.create(
            modulo=nuevo,
            titulo=c.titulo,
            descripcion=c.descripcion,
            orden=c.orden,
            visible=c.visible,
            fecha_inicio=mover(c.fecha_inicio),
            fecha_fin=mover(c.fecha_fin),
            estado="auto",
        )
        for copiar in COPIADORES:
            copiar(c, copia, mover)
    return nuevo
