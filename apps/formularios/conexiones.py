"""Cómo los formularios se muestran dentro de las clases, el inicio, el módulo, «Por calificar» y el libro de notas."""

from datetime import timedelta

from django.db.models import Count, Exists, OuterRef
from django.urls import reverse
from django.utils import timezone

from apps.academico import contenido, resumen
from apps.academico import models as academico
from apps.cuentas import resumen as resumen_cuentas
from apps.nucleo.utils import nota_fmt, plural, vencimiento_texto

from .models import Formulario, Intento


def _url(f):
    return reverse("formularios:ver", args=[f.pk])


def _estados_del_alumno(alumno, ids):
    """Por formulario: cuántos intentos terminó, su mejor nota (ya revisada) y cuántos faltan revisar."""
    datos = {}
    for fila in Intento.objects.filter(alumno=alumno, formulario__in=ids, fin__isnull=False).values(
        "formulario", "revisado", "nota"
    ):
        d = datos.setdefault(fila["formulario"], {"hechos": 0, "mejor": None, "por_revisar": 0})
        d["hechos"] += 1
        if not fila["revisado"]:
            d["por_revisar"] += 1
        elif fila["nota"] is not None and (d["mejor"] is None or fila["nota"] > d["mejor"]):
            d["mejor"] = fila["nota"]
    return datos


def _conteos_del_docente(ids):
    """Por formulario: cuántos alumnos ya respondieron y cuántos intentos faltan revisar."""
    terminados = Intento.objects.filter(formulario__in=ids, fin__isnull=False)
    rindieron = {x["formulario"]: x["n"] for x in terminados.values("formulario").annotate(n=Count("alumno", distinct=True))}
    pendientes = {x["formulario"]: x["n"] for x in terminados.filter(revisado=False).values("formulario").annotate(n=Count("id"))}
    return rindieron, pendientes


def _ver_para_alumno(modulo):
    """Formularios publicados del módulo que el alumno puede ver (las clases que no empiezan o están ocultas no se muestran)."""
    consulta = Formulario.objects.filter(clase__modulo=modulo, publicado=True, clase__visible=True).select_related(
        "clase__modulo"
    )
    return [f for f in consulta if not f.de_clase_proxima]


def _item_alumno(f, estado):
    hecha = estado["hechos"] > 0
    nota = f" · Tu nota: {nota_fmt(estado['mejor'])}" if estado["mejor"] is not None else ""
    return contenido.ItemClase(
        clase_id=f.clase_id,
        tipo="examen",
        titulo=f.titulo,
        url=_url(f),
        icono="examen",
        color="ico-azul",
        detalle=f.nombre_modo + (f" · {f.tiempo_minutos} min" if f.tiempo_minutos else ""),
        boton="Dar el examen" if f.es_examen else "Responder",
        boton_modulo="Responder las preguntas",
        boton_clase="Responder las preguntas",
        limite=f.fecha_limite,
        hecha=hecha,
        cuenta_en_avance=not f.es_encuesta,
        abierta=f.abierto,
        clase_titulo=f.clase.titulo,
        modulo_nombre=f.clase.modulo.nombre,
        modulo_id=f.clase.modulo_id,
        id=f.pk,
        resultado=f"Ya respondiste{nota}" if hecha else "",
    )


def _item_docente(f, rindieron, por_revisar):
    chips = []
    if not f.publicado:
        chips.append(("Sin publicar", "chip-aviso"))
    chips.append((f"{rindieron} respondieron", "chip-gris"))
    return contenido.ItemClase(
        clase_id=f.clase_id,
        tipo="examen",
        titulo=f.titulo,
        url=_url(f),
        icono="examen",
        color="ico-azul",
        detalle=f"Formulario · {f.nombre_modo}",
        chip=f"{rindieron} respondieron",
        chip_clase="chip-gris",
        limite=f.fecha_limite,
        clase_titulo=f.clase.titulo,
        modulo_nombre=f.clase.modulo.nombre,
        modulo_id=f.clase.modulo_id,
        id=f.pk,
        extra={"chips": chips, "entregaron": rindieron, "sin_calificar": por_revisar},
    )


def proveedor(modulo, usuario, acceso):
    """Los formularios de las clases del módulo, para quien los ve."""
    if acceso == "alumno":
        formularios = _ver_para_alumno(modulo)
        estados = _estados_del_alumno(usuario, [f.pk for f in formularios])
        return [_item_alumno(f, estados.get(f.pk, {"hechos": 0, "mejor": None, "por_revisar": 0})) for f in formularios]
    formularios = list(Formulario.objects.filter(clase__modulo=modulo).select_related("clase__modulo"))
    rindieron, pendientes = _conteos_del_docente([f.pk for f in formularios])
    return [_item_docente(f, rindieron.get(f.pk, 0), pendientes.get(f.pk, 0)) for f in formularios]


def formularios_del_modulo(modulo, usuario, acceso):
    """La lista «Formularios y exámenes» de la pestaña Tareas del módulo."""
    if acceso == "alumno":
        formularios = sorted(_ver_para_alumno(modulo), key=lambda f: f.fecha_limite, reverse=True)
        estados = _estados_del_alumno(usuario, [f.pk for f in formularios])
        rindieron = pendientes = {}
    else:
        formularios = list(Formulario.objects.filter(clase__modulo=modulo).select_related("clase__modulo"))
        estados = {}
        rindieron, pendientes = _conteos_del_docente([f.pk for f in formularios])
    preguntas = {f.pk: f for f in Formulario.con_resumen(formularios)}
    total_alumnos = getattr(modulo, "total_alumnos", None)
    if total_alumnos is None:
        total_alumnos = modulo.matriculas.count()
    items = []
    for f in formularios:
        f = preguntas[f.pk]
        detalle = f"{f.nombre_modo} · {vencimiento_texto(f.fecha_limite)} · {plural(f.total_preguntas, 'pregunta', 'preguntas')}"
        if acceso == "alumno":
            e = estados.get(f.pk, {"hechos": 0, "mejor": None, "por_revisar": 0})
            if e["mejor"] is not None:
                chip, clase = f"Nota {nota_fmt(e['mejor'])}", "chip-info"
            elif e["por_revisar"]:
                chip, clase = "Por revisar", "chip-gris"
            elif e["hechos"]:
                chip, clase = "Respondido", "chip-ok"
            elif f.abierto:
                chip, clase = "Por responder", "chip-aviso"
            elif f.vencido:
                chip, clase = "No respondiste", "chip-mal"
            else:
                chip, clase = "Todavía no abre", "chip-gris"
        else:
            detalle += f" · {rindieron.get(f.pk, 0)} de {total_alumnos} respondieron"
            if not f.publicado:
                chip, clase = "Borrador", "chip-gris"
            elif pendientes.get(f.pk):
                chip, clase = f"{pendientes[f.pk]} por revisar", "chip-aviso"
            elif f.vencido:
                chip, clase = "Cerrado", "chip-gris"
            else:
                chip, clase = "Publicado", "chip-info"
        items.append(
            contenido.ItemClase(
                clase_id=f.clase_id, tipo="examen", titulo=f.titulo, url=_url(f), icono="examen", color="ico-azul",
                detalle=detalle, chip=chip, chip_clase=clase, limite=f.fecha_limite, id=f.pk,
            )
        )  # fmt: skip
    return items


def pendientes_de_alumno(alumno):
    """Formularios de los módulos activos del alumno que todavía no respondió y que aún puede responder."""
    hechos = Intento.objects.filter(formulario=OuterRef("pk"), alumno=alumno, fin__isnull=False)
    formularios = (
        Formulario.objects.filter(
            clase__modulo__matriculas__alumno=alumno,
            clase__modulo__activo=True,
            clase__visible=True,
            publicado=True,
            fecha_limite__gt=timezone.now(),
        )
        .annotate(hecho=Exists(hechos))
        .filter(hecho=False)
        .select_related("clase__modulo")
        .order_by("fecha_limite")
    )
    return [_item_alumno(f, {"hechos": 0, "mejor": None, "por_revisar": 0}) for f in formularios if f.abierto]


def _por_revisar_del_docente(docente):
    return (
        Intento.objects.filter(
            formulario__eliminado__isnull=True,
            formulario__clase__modulo__docente=docente,
            formulario__clase__modulo__activo=True,
            fin__isnull=False,
            revisado=False,
        )
        .select_related("alumno", "formulario__clase__modulo")
        .order_by("fin")
    )


def por_calificar(modulo):
    return Intento.objects.filter(
        formulario__clase__modulo=modulo, formulario__eliminado__isnull=True, fin__isnull=False, revisado=False
    ).count()


def esperando_nota(docente):
    return [
        (reverse("formularios:intento", args=[i.pk]), i.formulario.clase.modulo_id) for i in _por_revisar_del_docente(docente)
    ]


def bandeja_pendientes(docente):
    """Los tests y trabajos terminados que esperan la revisión del docente, con la forma de la bandeja «Por calificar»."""
    return [
        {
            "clave": f"i{i.pk}", "tipo": "examen", "enlace": reverse("formularios:intento", args=[i.pk]),
            "nombres": i.alumno.nombres, "apellidos": i.alumno.apellidos, "iniciales": i.alumno.iniciales,
            "titulo": i.formulario.titulo, "modo": i.formulario.nombre_modo, "curso_id": i.formulario.clase.modulo_id,
            "curso": i.formulario.clase.modulo.nombre, "fecha": i.fin, "tardia": False, "archivo": None, "archivo_nombre": "",
            "es_imagen": False, "instrucciones": "", "criterios": [], "tipo_calificacion": "nota", "nota": None, "aprobado": None,
            "comentario_alumno": "", "resultado": "",
        }
        for i in _por_revisar_del_docente(docente)
    ]  # fmt: skip


def proximas_de_docente(docente, dias=21):
    ahora = timezone.now()
    formularios = list(
        Formulario.objects.filter(
            clase__modulo__docente=docente,
            clase__modulo__activo=True,
            fecha_limite__gte=ahora,
            fecha_limite__lte=ahora + timedelta(days=dias),
        )
        .select_related("clase__modulo")
        .order_by("fecha_limite")[:8]
    )
    rindieron, _pendientes = _conteos_del_docente([f.pk for f in formularios])
    items = []
    for f in formularios:
        n = rindieron.get(f.pk, 0)
        items.append(
            contenido.ItemClase(
                clase_id=f.clase_id, tipo="examen", titulo=f.titulo, url=_url(f), icono="examen", color="ico-azul",
                detalle=f.nombre_modo, limite=f.fecha_limite, clase_titulo=f.clase.titulo, modulo_nombre=f.clase.modulo.nombre,
                modulo_id=f.clase.modulo_id, id=f.pk,
                extra={"entregaron": n, "texto_entregas": "1 respondió" if n == 1 else f"{n} respondieron"},
            )
        )  # fmt: skip
    return items


def actividades_con_nota(modulo):
    """Los tests y trabajos publicados del módulo como actividades del libro de notas (las encuestas no llevan nota)."""
    formularios = Formulario.objects.filter(clase__modulo=modulo, publicado=True).exclude(modo="encuesta").select_related("clase")
    return [
        {
            "clave": f"q{f.pk}", "id": f.pk, "titulo": f.titulo, "fecha_limite": f.fecha_limite, "tipo_calificacion": "nota",
            "tipo": "examen", "modo": f.modo, "clase": f.clase, "etiqueta": ("Trabajo" if f.modo == "trabajo" else "Examen") + ": ",
            "url": _url(f),
        }
        for f in formularios
    ]  # fmt: skip


def estados_de_actividades(modulo):
    """Por alumno y formulario: su mejor nota ya revisada (o None si todavía falta revisar)."""
    estados = {}
    terminados = Intento.objects.filter(
        formulario__clase__modulo=modulo, formulario__eliminado__isnull=True, fin__isnull=False
    ).values("alumno", "formulario", "revisado", "nota")
    for i in terminados:
        e = estados.setdefault(i["alumno"], {}).setdefault(
            f"q{i['formulario']}", {"nota": None, "aprobado": None, "entrego": True, "comentario": None}
        )
        if i["revisado"] and i["nota"] is not None and (e["nota"] is None or float(i["nota"]) > e["nota"]):
            e["nota"] = float(i["nota"])
    return estados


def calificacion_del_modulo(modulo):
    """(tests y trabajos calificados, esperando revisión) del módulo."""
    terminados = Intento.objects.filter(
        formulario__clase__modulo=modulo, formulario__eliminado__isnull=True, fin__isnull=False
    ).exclude(formulario__modo="encuesta")
    pendientes = terminados.filter(revisado=False).count()
    return terminados.count() - pendientes, pendientes


def copiar_contenido(origen, nueva, mover):
    """Copia los formularios de una clase (con sus preguntas e imágenes propias y las fechas corridas) a la clase nueva."""
    for f in Formulario.objects.filter(clase=origen).order_by("id"):
        f.copiar_a(nueva, mover)


def conectar():
    from apps.academico import copia, papelera
    from apps.nucleo import menu

    menu.registrar_contador("inicio", lambda alumno: len(pendientes_de_alumno(alumno)) if alumno.rol == "alumno" else 0)
    menu.registrar_contador(
        "calificar", lambda docente: _por_revisar_del_docente(docente).count() if docente.rol == "docente" else 0
    )
    copia.registrar_copiador(copiar_contenido)
    papelera.registrar("formulario", "Formulario", "examen", "ico-azul", Formulario)
    contenido.PROVEEDORES.append(proveedor)
    contenido.FORMULARIOS_DEL_MODULO.append(formularios_del_modulo)
    contenido.PENDIENTES_DE_ALUMNO.append(pendientes_de_alumno)
    contenido.POR_CALIFICAR.append(por_calificar)
    contenido.ESPERANDO_NOTA.append(esperando_nota)
    contenido.BANDEJA_PENDIENTES.append(bandeja_pendientes)
    contenido.PROXIMAS_DE_DOCENTE.append(proximas_de_docente)
    contenido.ACTIVIDADES_CON_NOTA.append(actividades_con_nota)
    contenido.ESTADOS_DE_ACTIVIDADES.append(estados_de_actividades)
    contenido.CALIFICACION_DEL_MODULO.append(calificacion_del_modulo)
    # Lo que se cuenta al eliminar un módulo y lo que ya son registros de los alumnos
    resumen.registrar_contador("formulario", "formularios", lambda m: Formulario.todos.filter(clase__modulo=m).count())
    resumen.registrar_contador(
        "test rendido", "tests rendidos", lambda m: Intento.objects.filter(formulario__clase__modulo=m).count()
    )
    resumen.registrar_registros_de_alumnos(lambda m: Intento.objects.filter(formulario__clase__modulo=m).exists())
    resumen_cuentas.registrar_contador(30, "test rendido", "tests rendidos", lambda u: Intento.objects.filter(alumno=u).count())
    # Una clase con formularios (incluso en la papelera) no se borra
    academico.CONTENIDO_DE_CLASE.append(lambda c: Formulario.todos.filter(clase=c).exists())
