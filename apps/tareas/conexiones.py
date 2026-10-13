"""Cómo las tareas y los materiales se muestran dentro de las clases, el inicio, el módulo y «Por calificar»."""

from datetime import timedelta

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from apps.academico import contenido, resumen
from apps.academico import models as academico
from apps.cuentas import resumen as resumen_cuentas
from apps.nucleo import archivos
from apps.nucleo.utils import nota_fmt

from .models import Entrega, Material, Tarea

COLORES_MATERIAL = {
    "PDF": "ico-rojo", "Word": "ico-azul", "PPT": "ico-ambar", "Excel": "ico-verde",
    "Foto": "ico-verde", "Video": "ico-azul", "Enlace": "ico-gris", "Archivo": "ico-gris",
}  # fmt: skip


def _item_material(m, es_docente):
    et = m.etiqueta
    es_video, es_enlace = et == "Video", et == "Enlace"
    return contenido.ItemClase(
        clase_id=m.clase_id,
        tipo="material",
        titulo=m.titulo,
        url=reverse("tareas:material", args=[m.pk]),
        icono="play" if es_video else ("enlace" if es_enlace else ""),
        etiqueta="" if (es_video or es_enlace) else et,
        color=COLORES_MATERIAL.get(et, "ico-gris"),
        accion="Ver" if es_video else ("Descargar" if m.tipo == "archivo" else "Abrir"),
        detalle="Toca para abrir"
        if m.tipo == "archivo"
        else ("Toca para ver el video" if es_video else "Toca para abrir el enlace"),
        nueva_pestana=m.tipo != "archivo",
        id=m.pk,
        extra={"borrar_url": reverse("tareas:material_eliminar", args=[m.pk]) if es_docente else ""},
    )


def _texto_resultado(entrega):
    if entrega.nota is not None:
        return f"Ya la entregaste · Tu nota: {nota_fmt(entrega.nota)}"
    if entrega.aprobado is not None:
        return "Ya la entregaste · " + ("Aprobaste" if entrega.aprobado else "No aprobaste")
    return "Ya la entregaste · falta que tu profesor la califique"


def _item_tarea_alumno(t, entrega):
    hecha = entrega is not None
    if hecha and entrega.calificada:
        chip, clase_chip = (f"Nota {nota_fmt(entrega.nota)}" if entrega.nota is not None else entrega.resultado_texto), "chip-ok"
    elif hecha:
        chip, clase_chip = "Hecha", "chip-ok"
    else:
        chip, clase_chip = "Por entregar", "chip-aviso"
    return contenido.ItemClase(
        clase_id=t.clase_id, tipo="tarea", titulo=t.titulo, url=reverse("tareas:ver", args=[t.pk]), icono="camara", color="ico-ambar",
        detalle="Entregar foto o archivo", boton="Subir foto o archivo", boton_clase="Entregar foto o archivo", chip=chip, chip_clase=clase_chip, limite=t.fecha_limite,
        hecha=hecha, cuenta_en_avance=True, abierta=t.acepta_entregas, clase_titulo=t.clase.titulo, modulo_nombre=t.clase.modulo.nombre,
        modulo_id=t.clase.modulo_id, id=t.pk, resultado=_texto_resultado(entrega) if hecha else "",
    )  # fmt: skip


def _item_tarea_docente(t):
    entregaron, sin = t.entregaron, t.sin_calificar
    chips = [(f"{entregaron} entregaron", "chip-gris")]
    if sin:
        chips.append((f"{sin} por calificar", "chip-aviso"))
    return contenido.ItemClase(
        clase_id=t.clase_id, tipo="tarea", titulo=t.titulo, url=reverse("tareas:ver", args=[t.pk]), icono="camara", color="ico-ambar",
        detalle="Entregar foto o archivo", chip=f"{entregaron} entregaron", chip_clase="chip-gris", limite=t.fecha_limite,
        clase_titulo=t.clase.titulo, modulo_nombre=t.clase.modulo.nombre, modulo_id=t.clase.modulo_id, id=t.pk,
        extra={"chips": chips, "entregaron": entregaron, "sin_calificar": sin},
    )  # fmt: skip


def con_conteos(consulta):
    """Tareas con cuántos entregaron y cuántos faltan por calificar (vista del docente)."""
    return consulta.annotate(
        entregaron=Count("entregas", distinct=True),
        sin_calificar=Count("entregas", filter=Q(entregas__nota__isnull=True, entregas__aprobado__isnull=True), distinct=True),
    )


def tareas_del_modulo(modulo, usuario, acceso):
    """Tareas del módulo para quien las ve: (tarea, entrega del alumno o None). El alumno no ve las de clases que no empiezan."""
    consulta = Tarea.objects.filter(clase__modulo=modulo).select_related("clase__modulo").order_by("-fecha_limite", "id")
    if acceso == "alumno":
        entregas = {e.tarea_id: e for e in Entrega.objects.filter(alumno=usuario, tarea__clase__modulo=modulo)}
        return [(t, entregas.get(t.pk)) for t in consulta.filter(clase__visible=True) if not t.de_clase_proxima]
    return [(t, None) for t in con_conteos(consulta)]


def proveedor(modulo, usuario, acceso):
    es_alumno, es_docente = acceso == "alumno", acceso == "docente"
    materiales = Material.objects.filter(clase__modulo=modulo).select_related("clase")
    if es_alumno:
        materiales = [m for m in materiales.filter(clase__visible=True) if m.clase.situacion != "proxima"]
    items = [_item_material(m, es_docente) for m in materiales]
    for t, entrega in tareas_del_modulo(modulo, usuario, acceso):
        items.append(_item_tarea_alumno(t, entrega) if es_alumno else _item_tarea_docente(t))
    return items


def pendientes_de_alumno(alumno):
    """Tareas de los módulos activos del alumno que todavía no entregó y que aún puede entregar."""
    tareas = (
        Tarea.objects.filter(clase__modulo__matriculas__alumno=alumno, clase__modulo__activo=True, clase__visible=True)
        .exclude(entregas__alumno=alumno)
        .select_related("clase__modulo")
        .order_by("fecha_limite")
    )
    return [
        contenido.ItemClase(
            clase_id=t.clase_id, tipo="tarea", titulo=t.titulo, url=reverse("tareas:ver", args=[t.pk]), icono="camara", color="ico-ambar",
            boton="Subir foto o archivo", limite=t.fecha_limite, cuenta_en_avance=True, clase_titulo=t.clase.titulo,
            modulo_nombre=t.clase.modulo.nombre, modulo_id=t.clase.modulo_id, id=t.pk,
        )
        for t in tareas
        if t.acepta_entregas
    ]  # fmt: skip


def por_calificar(modulo):
    return Entrega.sin_calificar().filter(tarea__clase__modulo=modulo).count()


def esperando_nota(docente):
    entregas = Entrega.sin_calificar().filter(tarea__clase__modulo__docente=docente, tarea__clase__modulo__activo=True)
    return [(reverse("tareas:calificar", args=[e.pk]), e.tarea.clase.modulo_id) for e in entregas.select_related("tarea__clase")]


def proximas_de_docente(docente, dias=21):
    ahora = timezone.now()
    tareas = con_conteos(
        Tarea.objects.filter(
            clase__modulo__docente=docente,
            clase__modulo__activo=True,
            fecha_limite__gte=ahora,
            fecha_limite__lte=ahora + timedelta(days=dias),
        ).select_related("clase__modulo")
    ).order_by("fecha_limite")[:8]
    items = []
    for t in tareas:
        item = _item_tarea_docente(t)
        item.extra["texto_entregas"] = "1 entregó" if t.entregaron == 1 else f"{t.entregaron} entregaron"
        items.append(item)
    return items


def notas_nuevas(alumno, limite=3):
    """Notas de los últimos 7 días (para el Inicio)."""
    desde = timezone.now() - timedelta(days=7)
    entregas = (
        Entrega.objects.filter(alumno=alumno, calificado__gte=desde)
        .select_related("tarea__clase__modulo")
        .order_by("-calificado")[:limite]
    )
    return [
        {"titulo": e.tarea.titulo, "modulo_nombre": e.tarea.clase.modulo.nombre, "nota_texto": nota_fmt(e.nota) if e.nota is not None else e.resultado_texto}
        for e in entregas
    ]  # fmt: skip


def actividades_con_nota(modulo):
    """Las tareas del módulo como actividades del libro de notas."""
    return [
        {
            "clave": f"t{t.pk}", "id": t.pk, "titulo": t.titulo, "fecha_limite": t.fecha_limite, "tipo_calificacion": t.tipo_calificacion,
            "tipo": "tarea", "modo": "", "clase": t.clase, "etiqueta": "", "url": reverse("tareas:ver", args=[t.pk]),
        }
        for t in Tarea.objects.filter(clase__modulo=modulo).select_related("clase")
    ]  # fmt: skip


def estados_de_actividades(modulo):
    estados = {}
    for e in Entrega.objects.filter(tarea__clase__modulo=modulo, tarea__eliminado__isnull=True):
        estados.setdefault(e.alumno_id, {})[f"t{e.tarea_id}"] = {
            "nota": float(e.nota) if e.nota is not None else None,
            "aprobado": e.aprobado,
            "entrego": True,
            "comentario": e.comentario_docente or None,
        }
    return estados


def calificacion_del_modulo(modulo):
    """(trabajos calificados, trabajos esperando nota) del módulo."""
    entregas = Entrega.objects.filter(tarea__clase__modulo=modulo)
    pendientes = entregas.filter(nota__isnull=True, aprobado__isnull=True).count()
    return entregas.count() - pendientes, pendientes


def copiar_contenido(origen, nueva, mover):
    """Copia los materiales y las tareas de una clase a la clase nueva (con archivos propios y fechas corridas)."""
    for m in Material.objects.filter(clase=origen).order_by("id"):
        Material.objects.create(
            clase=nueva, titulo=m.titulo, descripcion=m.descripcion, tipo=m.tipo, archivo_ruta=archivos.copiar(m.archivo_ruta) or "",
            archivo_nombre=m.archivo_nombre, url=m.url,
        )  # fmt: skip
    for t in Tarea.objects.filter(clase=origen).order_by("id"):
        Tarea.objects.create(
            clase=nueva, titulo=t.titulo, instrucciones=t.instrucciones, criterios=t.criterios, archivo_ruta=archivos.copiar(t.archivo_ruta) or "",
            archivo_nombre=t.archivo_nombre, fecha_limite=mover(t.fecha_limite), puntaje_max=t.puntaje_max, politica_tardia=t.politica_tardia,
            penalidad_puntos=t.penalidad_puntos, tipo_calificacion=t.tipo_calificacion, tipo=t.tipo,
        )  # fmt: skip


def conectar():
    from apps.academico import copia, papelera
    from apps.nucleo import menu

    menu.registrar_contador("inicio", lambda alumno: len(pendientes_de_alumno(alumno)) if alumno.rol == "alumno" else 0)
    menu.registrar_contador("calificar", lambda docente: len(esperando_nota(docente)) if docente.rol == "docente" else 0)
    copia.registrar_copiador(copiar_contenido)
    papelera.registrar("tarea", "Tarea", "camara", "ico-ambar", Tarea)
    papelera.registrar("material", "Material", "carpeta", "ico-gris", Material)
    contenido.PROVEEDORES.append(proveedor)
    contenido.CALIFICACION_DEL_MODULO.append(calificacion_del_modulo)
    contenido.ACTIVIDADES_CON_NOTA.append(actividades_con_nota)
    contenido.ESTADOS_DE_ACTIVIDADES.append(estados_de_actividades)
    contenido.PENDIENTES_DE_ALUMNO.append(pendientes_de_alumno)
    contenido.POR_CALIFICAR.append(por_calificar)
    contenido.ESPERANDO_NOTA.append(esperando_nota)
    contenido.PROXIMAS_DE_DOCENTE.append(proximas_de_docente)
    contenido.NOTAS_NUEVAS.append(notas_nuevas)
    # Lo que se cuenta al eliminar un módulo y lo que ya son registros de los alumnos
    resumen.registrar_contador("material", "materiales", lambda m: Material.todos.filter(clase__modulo=m).count())
    resumen.registrar_contador("tarea", "tareas", lambda m: Tarea.todos.filter(clase__modulo=m).count())
    resumen.registrar_contador(
        "trabajo entregado", "trabajos entregados", lambda m: Entrega.objects.filter(tarea__clase__modulo=m).count()
    )
    resumen.registrar_registros_de_alumnos(lambda m: Entrega.objects.filter(tarea__clase__modulo=m).exists())
    resumen_cuentas.registrar_contador(
        10, "trabajo entregado", "trabajos entregados", lambda u: Entrega.objects.filter(alumno=u).count()
    )
    # Una clase con materiales o tareas (incluso en la papelera) no se borra
    academico.CONTENIDO_DE_CLASE.append(lambda c: Material.todos.filter(clase=c).exists() or Tarea.todos.filter(clase=c).exists())
