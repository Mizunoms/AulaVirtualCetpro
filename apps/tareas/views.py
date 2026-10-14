"""Materiales, tareas, entregas y calificación (mismas pantallas y direcciones que el sistema anterior)."""

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.academico import contenido
from apps.academico.models import Clase, Evaluacion, Modulo
from apps.academico.views import cargar_modulo, modulo_del_docente
from apps.cuentas.models import Rol
from apps.nucleo import archivos
from apps.nucleo.models import Notificacion, Registro
from apps.nucleo.permisos import Detener, exigir, no_encontrado, prohibido
from apps.nucleo.utils import error, nota_fmt, ok, por_metodo, url_absoluta, vista, volver_con_error

from .conexiones import tareas_del_modulo
from .models import (
    Entrega,
    Material,
    PoliticaTardia,
    Tarea,
    TipoCalificacion,
    TipoMaterial,
    TipoTarea,
    criterios_de_texto,
    es_enlace_valido,
)


def _entrada(request, clave, defecto=""):
    return (request.POST.get(clave) or defecto).strip()


def _archivo_enviado(request, campo):
    f = request.FILES.get(campo)
    return f if f is not None and f.size > 0 else None


def _guardar_archivo(request, campo, volver):
    """Guarda el archivo del campo y devuelve (ruta, nombre). Si algo falla, vuelve con el mensaje."""
    try:
        return archivos.guardar(request.FILES.get(campo))
    except archivos.ArchivoError as ex:
        raise Detener(volver_con_error(request, volver, str(ex))) from ex


def _enviar(ruta, nombre, es_imagen_o_pdf=False):
    return archivos.enviar(ruta, nombre, en_linea=es_imagen_o_pdf)


def _en_linea(ruta, nombre):
    return archivos.es_imagen(ruta) or (nombre or "").lower().endswith(".pdf")


# ===================================================================== Materiales


@require_POST
@exigir(Rol.DOCENTE)
def material_guardar(request, id):
    m = modulo_del_docente(request, id)
    clase_id = _entrada(request, "unidad_id")
    clase = Clase.objects.filter(pk=clase_id, modulo=m).first() if clase_id.isdigit() else None
    if clase is None:
        return volver_con_error(
            request, reverse("academico:modulo", args=[id]) + "#clases", "Elige la clase donde va el material."
        )
    volver = reverse("academico:clase", args=[clase.pk])
    titulo = _entrada(request, "titulo")[:150]
    tipo = TipoMaterial.ENLACE if _entrada(request, "tipo") == "enlace" else TipoMaterial.ARCHIVO
    datos = {"clase": clase, "titulo": titulo, "tipo": tipo}
    if tipo == TipoMaterial.ENLACE:
        enlace = _entrada(request, "url")
        if not es_enlace_valido(enlace):
            return volver_con_error(
                request, volver, "El enlace no es válido. Copia la dirección completa (empieza con https://)."
            )
        datos["url"] = enlace[:500]
        if any(x in enlace.lower() for x in ("youtube.com", "youtu.be")):
            datos["tipo"] = TipoMaterial.VIDEO
        datos["titulo"] = titulo or ("Video" if datos["tipo"] == TipoMaterial.VIDEO else "Enlace")
    else:
        if _archivo_enviado(request, "archivo") is None:
            return volver_con_error(request, volver, "Elige el archivo que quieres subir.")
        ruta, nombre = _guardar_archivo(request, "archivo", volver)
        datos.update(archivo_ruta=ruta, archivo_nombre=nombre, titulo=titulo or nombre.rsplit(".", 1)[0])
    Material.objects.create(**datos)
    ok(request, "Material publicado. Tus alumnos ya lo ven.")
    return redirect(volver)


@exigir()
def material_ver(request, id):
    """Abre o descarga un material (con permisos)."""
    m = Material.objects.filter(pk=id).select_related("clase").first()
    if m is None:
        return no_encontrado(request)
    _modulo, acceso = cargar_modulo(request, m.clase.modulo_id)
    if acceso == "alumno" and m.clase.situacion == "proxima":
        return no_encontrado(request)  # la clase todavía no empieza
    if m.tipo != TipoMaterial.ARCHIVO:
        return HttpResponseRedirect(m.url)
    return _enviar(m.archivo_ruta, m.archivo_nombre, _en_linea(m.archivo_ruta, m.archivo_nombre))


@require_POST
@exigir(Rol.DOCENTE)
def material_eliminar(request, id):
    m = Material.objects.filter(pk=id).select_related("clase").first()
    if m is None:
        return no_encontrado(request)
    modulo_del_docente(request, m.clase.modulo_id)
    m.eliminado = timezone.now()  # va a la papelera; el archivo se borra a los 30 días
    m.save(update_fields=["eliminado"])
    ok(request, "Material enviado a la papelera. Puedes recuperarlo durante 30 días.")
    return redirect("academico:clase", id=m.clase_id)


# ===================================================================== Tareas


@exigir()
def index(request, id):
    """Tareas y formularios del módulo."""
    m, acceso = cargar_modulo(request, id)
    tareas = tareas_del_modulo(m, request.user, acceso)
    filas = []
    for t, entrega in tareas:
        if acceso == "alumno":
            if entrega is not None and entrega.calificada:
                chip, clase = (
                    (f"Nota {nota_fmt(entrega.nota)}" if entrega.nota is not None else entrega.resultado_texto),
                    "chip-info",
                )
            elif entrega is not None:
                chip, clase = "Entregada", "chip-ok"
            elif t.acepta_entregas:
                chip, clase = "Por entregar", "chip-aviso"
            else:
                chip, clase = "No entregada", "chip-mal"
            detalle = ""
        else:
            if t.sin_calificar:
                chip, clase = f"{t.sin_calificar} por calificar", "chip-aviso"
            elif t.vencida:
                chip, clase = "Cerrada", "chip-gris"
            else:
                chip, clase = "Abierta", "chip-info"
            detalle = f" · {t.entregaron} de {m.total_alumnos} {'entregó' if t.entregaron == 1 else 'entregaron'}"
        filas.append({"tarea": t, "chip": chip, "chip_clase": clase, "detalle": detalle})
    return vista(
        request,
        "tareas/index.html",
        {
            "modulo": m,
            "acceso": acceso,
            "es_docente": acceso == "docente",
            "es_alumno": acceso == "alumno",
            "filas": filas,
            "formularios": contenido.formularios_del_modulo(m, request.user, acceso),
        },
        titulo="Tareas y exámenes",
        sub=m.nombre,
        volver=reverse("academico:modulo", args=[id]),
        menu="cursos",
    )


def _clases_numeradas(modulo):
    clases = list(modulo.clases.all())
    for n, c in enumerate(clases, start=1):
        c.n = n
    return clases


def _filas_criterios(request):
    old = request.session.get("_old", {})
    textos = old.get("criterio_texto[]") or ["", "", ""]
    puntos = old.get("criterio_puntos[]") or []
    ejemplos = ["Foto de frente y de perfil, con buena luz", "Corte parejo a los dos lados", "Modelo con capa y cabello seco"]
    return [
        {
            "texto": t,
            "puntos": puntos[i] if i < len(puntos) else "",
            "ejemplo": ejemplos[i] if i < len(ejemplos) else "Lo que vas a revisar",
        }
        for i, t in enumerate(textos)
    ]


@exigir(Rol.DOCENTE)
def crear(request, id):
    m = modulo_del_docente(request, id)
    clase_id = request.GET.get("clase", "")
    clase = Clase.objects.filter(pk=clase_id, modulo=m).first() if clase_id.isdigit() else None
    clases = _clases_numeradas(m)
    actual = Clase.actual(clases)
    old = request.session.get("_old", {})
    elegida = old.get("unidad_id") or (str(clase.pk) if clase else (str(actual.pk) if actual else ""))
    return vista(
        request,
        "tareas/crear.html",
        {
            "modulo": m,
            "clases": clases,
            "clase_elegida": elegida,
            "fecha_defecto": (timezone.localdate() + timedelta(days=7)).isoformat(),
            "tardia_sel": old.get("politica_tardia", "penalidad"),
            "calif_sel": old.get("tipo_calificacion", "nota"),
            "tipo_sel": old.get("tipo", "individual"),
            "criterios_filas": _filas_criterios(request),
            "tiene_criterios": any(t.strip() for t in old.get("criterio_texto[]") or []),  # si volvió con errores, sigue abierto
            "politicas": [("no_acepta", "No"), ("acepta", "Sí"), ("penalidad", "Sí, restando puntos")],
            "calificaciones": [("nota", "Nota de 0 a 20"), ("rubrica", "Rúbrica (0 a 20)"), ("aprobado", "Aprobó / No aprobó")],
            "tipos": [("individual", "Individual"), ("grupal", "En grupo")],
            "tiene_titulo": bool(old.get("titulo")),
        },
        titulo="Nueva tarea",
        sub=f"Clase: {clase.titulo}" if clase else m.nombre,
        volver=(reverse("academico:clase", args=[clase.pk]) + "#crear") if clase else reverse("tareas:modulo", args=[id]),
        menu="cursos",
    )


def _criterios_del_formulario(request, volver):
    """Criterios de evaluación: filas «criterio_texto[]» con sus «criterio_puntos[]» (o, como antes, un texto con una línea por
    criterio). Se guardan como líneas «texto|puntos». Si hay puntos, deben sumar 20."""
    textos = request.POST.getlist("criterio_texto[]")
    if "criterio_texto[]" not in request.POST:
        lineas = [t.replace("|", " ").strip()[:150] for t in _entrada(request, "criterios").splitlines()]
        return "\n".join([x for x in lineas if x][:12])
    puntos = request.POST.getlist("criterio_puntos[]")
    filas = []
    for i, t in enumerate(textos):
        t = t.replace("|", " ").replace("\r", " ").replace("\n", " ").strip()[:150]
        if t:
            filas.append((t, (puntos[i] if i < len(puntos) else "").strip()))
    filas = filas[:12]
    if any(p for _t, p in filas):
        suma = 0
        for _t, p in filas:
            if not p.isdigit() or int(p) > 20:
                raise Detener(volver_con_error(request, volver, "Escribe los puntos de cada criterio (un número de 0 a 20)."))
            suma += int(p)
        if suma != 20:
            raise Detener(volver_con_error(request, volver, f"Los puntos de los criterios deben sumar 20. Ahora suman {suma}."))
    return "\n".join(t if not p else f"{t}|{int(p)}" for t, p in filas)


@require_POST
@exigir(Rol.DOCENTE)
def guardar(request, id):
    m = modulo_del_docente(request, id)
    volver = reverse("tareas:nueva", args=[id])
    titulo = _entrada(request, "titulo")[:150]
    try:
        limite = timezone.make_aware(
            datetime.strptime(f"{_entrada(request, 'fecha')} {_entrada(request, 'hora', '23:59')}", "%Y-%m-%d %H:%M")
        )
    except ValueError:
        limite = None
    if not titulo:
        return volver_con_error(request, volver, "Escribe el nombre de la tarea.")
    if limite is None:
        return volver_con_error(request, volver, "Elige hasta qué día se puede entregar.")
    clase_id = _entrada(request, "unidad_id")
    clase = Clase.objects.filter(pk=clase_id, modulo=m).first() if clase_id.isdigit() else None
    if clase is None:
        clase = Clase.ultima_o_crear(m)
    tardia = _entrada(request, "politica_tardia", "penalidad")
    calif = _entrada(request, "tipo_calificacion", "nota")
    tipo = _entrada(request, "tipo", "individual")
    try:
        penalidad = max(Decimal(0), min(Decimal(20), Decimal(_entrada(request, "penalidad_puntos", "2").replace(",", "."))))
    except InvalidOperation:
        penalidad = Decimal(2)
    politica = tardia if tardia in PoliticaTardia.values else PoliticaTardia.PENALIDAD
    datos = {
        "clase": clase,
        "titulo": titulo,
        "instrucciones": _entrada(request, "instrucciones")[:5000],
        "criterios": _criterios_del_formulario(request, volver),
        "fecha_limite": limite,
        "politica_tardia": politica,
        "penalidad_puntos": penalidad if politica == PoliticaTardia.PENALIDAD else 0,
        "tipo_calificacion": calif if calif in TipoCalificacion.values else TipoCalificacion.NOTA,
        "tipo": TipoTarea.GRUPAL if tipo == "grupal" else TipoTarea.INDIVIDUAL,
    }
    if _archivo_enviado(request, "archivo") is not None:
        datos["archivo_ruta"], datos["archivo_nombre"] = _guardar_archivo(request, "archivo", volver)
    t = Tarea.objects.create(**datos)
    if clase.situacion != "proxima":
        Notificacion.a_alumnos(m, f"Nueva tarea: {titulo}", reverse("tareas:ver", args=[t.pk]))
    ok(request, "¡Tarea publicada! Tus alumnos ya la ven en su Inicio.")
    return redirect(reverse("tareas:ver", args=[t.pk]) + "?publicada=1")


def _tarea_visible(request, id):
    t = Tarea.objects.filter(pk=id).select_related("clase__modulo__docente").first()
    if t is None:
        raise Detener(no_encontrado(request))
    m, acceso = cargar_modulo(request, t.clase.modulo_id)
    return t, m, acceso


@exigir()
def ver(request, id):
    """Alumno: ver y entregar. Docente: ver quién entregó."""
    t, m, acceso = _tarea_visible(request, id)
    pagina = {"titulo": t.titulo, "sub": m.nombre, "volver": reverse("tareas:modulo", args=[m.pk]), "menu": "cursos"}
    if acceso == "alumno":
        if t.de_clase_proxima:
            return no_encontrado(request)  # la clase todavía no empieza
        if request.GET.get("desde") == "inicio":
            pagina.update(volver=reverse("nucleo:inicio"), menu="inicio")
        entrega = Entrega.objects.filter(tarea=t, alumno=request.user).first()
        return vista(
            request,
            "tareas/alumno.html",
            {
                "tarea": t,
                "entrega": entrega,
                "calificada": bool(entrega and entrega.calificada),
                "puede_entregar": t.acepta_entregas,
                "vencida": t.vencida,
                "minima": Evaluacion.de(m).nota_minima,
                "criterios": criterios_de_texto(t.criterios),
                "clase_fecha": "chip-mal"
                if t.vencida
                else ("chip-aviso" if (t.fecha_limite - timezone.now()).total_seconds() < 86400 else "chip-info"),
            },
            **pagina,
        )
    entregas = {e.alumno_id: e for e in Entrega.objects.filter(tarea=t)}
    lista = []
    for a in m.alumnos():
        e = entregas.get(a.pk)
        lista.append({"alumno": a, "entrega": e, "enviada": e is not None, "calificada": bool(e and e.calificada)})
    # Primero los que entregaron y faltan por calificar, luego los ya calificados y al final los que no entregaron.
    lista.sort(key=lambda x: (not x["enviada"], x["calificada"], x["alumno"].apellidos, x["alumno"].nombres))
    entregaron = sum(1 for x in lista if x["enviada"])
    tarde = sum(1 for x in lista if x["enviada"] and x["entrega"].tardia)
    enlace = url_absoluta(request, reverse("tareas:ver", args=[t.pk]))
    texto_recordar = f'Recuerda entregar la tarea "{t.titulo}". {_vencimiento(t)}. {enlace}'
    return vista(
        request,
        "tareas/docente.html",
        {
            "tarea": t,
            "modulo": m,
            "acceso": acceso,
            "es_docente": acceso == "docente",
            "lista": lista,
            "publicada": "publicada" in request.GET,
            "a_tiempo": entregaron - tarde,
            "tarde": tarde,
            "faltan": len(lista) - entregaron,
            "texto_whatsapp": f'Nueva tarea en el aula virtual: "{t.titulo}". {_vencimiento(t)}. Entra aquí: {enlace}',
            "texto_recordar": texto_recordar,
        },
        **pagina,
    )


def _vencimiento(tarea):
    from apps.nucleo.utils import vencimiento_texto

    return vencimiento_texto(tarea.fecha_limite)


@require_POST
@exigir(Rol.ALUMNO)
def entregar(request, id):
    t, _m, acceso = _tarea_visible(request, id)
    if acceso != "alumno":
        return prohibido(request)
    volver = reverse("tareas:ver", args=[id])
    if not t.acepta_entregas:
        error(request, "La fecha ya pasó y esta tarea no acepta entregas tarde.")
        return redirect(volver)
    previa = Entrega.objects.filter(tarea=t, alumno=request.user).first()
    if previa and previa.calificada:
        error(request, "Esta tarea ya fue calificada; no se puede cambiar.")
        return redirect(volver)
    campo = "foto" if _archivo_enviado(request, "foto") else ("archivo" if _archivo_enviado(request, "archivo") else None)
    enlace = _entrada(request, "enlace")
    if campo is None and not enlace:
        error(request, "Toma una foto o elige un archivo antes de enviar.")
        return redirect(volver)
    datos = {
        "archivo_ruta": "",
        "archivo_nombre": "",
        "enlace": "",
        "comentario_alumno": _entrada(request, "comentario")[:2000],
        "tardia": t.vencida,
    }
    if campo is not None:
        try:
            datos["archivo_ruta"], datos["archivo_nombre"] = archivos.guardar(request.FILES[campo])
        except archivos.ArchivoError as ex:
            error(request, str(ex))
            return redirect(volver)
    else:
        if not es_enlace_valido(enlace):
            error(request, "El enlace no es válido. Copia la dirección completa.")
            return redirect(volver)
        datos["enlace"] = enlace[:500]
    anterior = previa.archivo_ruta if previa else ""
    Entrega.objects.update_or_create(tarea=t, alumno=request.user, defaults={**datos, "fecha_entrega": timezone.now()})
    if anterior:
        archivos.borrar(anterior)
    ok(request, "¡Tarea entregada! Te avisaremos cuando tenga nota.")
    return redirect(volver)


@exigir()
def archivo_de_tarea(request, id):
    """Archivo adjunto de la tarea (instrucciones del docente)."""
    t = Tarea.objects.filter(pk=id).select_related("clase").first()
    if t is None or not t.archivo_ruta:
        return no_encontrado(request)
    cargar_modulo(request, t.clase.modulo_id)
    return _enviar(t.archivo_ruta, t.archivo_nombre, archivos.es_imagen(t.archivo_ruta))


@require_POST
@exigir(Rol.DOCENTE)
def eliminar(request, id):
    t = Tarea.objects.filter(pk=id).select_related("clase").first()
    if t is None:
        return no_encontrado(request)
    modulo_del_docente(request, t.clase.modulo_id)
    t.eliminado = timezone.now()  # va a la papelera con sus entregas y notas; se borra de verdad a los 30 días
    t.save(update_fields=["eliminado"])
    ok(request, "Tarea enviada a la papelera. Puedes recuperarla (con sus entregas y notas) durante 30 días.")
    return redirect("academico:clase", id=t.clase_id)


# ===================================================================== Calificar


def _item_de_entrega(e, request):
    """Una entrega con lo que necesita la bandeja de calificación."""
    t, m = e.tarea, e.tarea.clase.modulo
    return {
        "clave": f"e{e.pk}", "tipo": "tarea", "enlace": reverse("tareas:calificar", args=[e.pk]),
        "nombres": e.alumno.nombres, "apellidos": e.alumno.apellidos, "iniciales": e.alumno.iniciales,
        "titulo": t.titulo, "modo": "Tarea", "curso_id": m.pk, "curso": m.nombre, "fecha": e.fecha_entrega, "tardia": e.tardia,
        "archivo": reverse("tareas:entrega_archivo", args=[e.pk]) if e.archivo_ruta else None, "archivo_nombre": e.archivo_nombre,
        "es_imagen": e.es_imagen, "instrucciones": t.instrucciones, "criterios": criterios_de_texto(t.criterios),
        "tipo_calificacion": t.tipo_calificacion, "nota": e.nota, "aprobado": e.aprobado, "comentario_alumno": e.comentario_alumno,
        "resultado": e.resultado_texto if e.calificada else "",
    }  # fmt: skip


def _consulta_de_entregas(docente):
    return Entrega.objects.filter(tarea__clase__modulo__docente=docente, tarea__clase__modulo__activo=True).select_related(
        "alumno", "tarea__clase__modulo"
    )


@exigir(Rol.DOCENTE)
def por_calificar(request):
    """Bandeja de calificación (docente): a la izquierda los trabajos y tests que esperan nota (o los calificados hace poco),
    con filtro por módulo y estado; a la derecha las pautas de lo que se eligió y el botón para calificar."""
    u = request.user
    pestana = "recientes" if request.GET.get("pestana") == "recientes" else "pendientes"
    modulo_txt = request.GET.get("modulo", "")
    modulo_id = int(modulo_txt) if modulo_txt.isdigit() else 0
    estado = request.GET.get("estado", "")
    estado = estado if estado in ("a_tiempo", "tarde") else ""

    base = _consulta_de_entregas(u)
    pendientes = [
        _item_de_entrega(e, request)
        for e in base.filter(nota__isnull=True, aprobado__isnull=True).order_by(
            "tarea__fecha_limite", "tarea_id", "fecha_entrega"
        )
    ]
    pendientes += contenido.bandeja_pendientes(u)
    pendientes.sort(key=lambda x: x["fecha"])
    recientes = [_item_de_entrega(e, request) for e in base.filter(calificado__isnull=False).order_by("-calificado")[:20]]
    lista = [
        x
        for x in (recientes if pestana == "recientes" else pendientes)
        if (modulo_id == 0 or x["curso_id"] == modulo_id) and (estado == "" or (estado == "tarde") == x["tardia"])
    ]
    seleccion = lista[0] if lista else None
    ver_clave = request.GET.get("ver", "")
    for x in lista:
        if x["clave"] == ver_clave:
            seleccion = x

    def enlace(**cambios):
        params = {
            "pestana": "recientes" if pestana == "recientes" else None,
            "modulo": modulo_id or None,
            "estado": estado or None,
        }
        params.update(cambios)
        qs = urlencode({k: v for k, v in params.items() if v not in (None, "")})
        return reverse("tareas:por_calificar") + (f"?{qs}" if qs else "")

    for x in lista:
        x["url_ver"] = enlace(ver=x["clave"])
    modulos = {m.pk: m.nombre for m in Modulo.objects.de_docente(u).order_by("nombre")}
    return vista(
        request,
        "entregas/por_calificar.html",
        {
            "pestana": pestana,
            "lista": lista,
            "seleccion": seleccion,
            "modulos": modulos,
            "modulo_id": modulo_id,
            "estado": estado,
            "cuenta_pendientes": len(pendientes),
            "hay_filtro": bool(modulo_id or estado),
            "url_pendientes": enlace(pestana=None, ver=None),
            "url_recientes": enlace(pestana="recientes", ver=None),
            "url_sin_filtros": reverse("tareas:por_calificar") + ("?pestana=recientes" if pestana == "recientes" else ""),
            "suma_criterios": sum(c["puntos"] or 0 for c in seleccion["criterios"])
            if seleccion and seleccion["tipo"] == "tarea"
            else 0,
            "base": reverse("tareas:por_calificar"),
        },
        titulo="Por calificar",
        sub="Trabajos que esperan tu nota",
        menu="calificar",
    )


def _entrega_del_docente(request, id):
    e = Entrega.objects.filter(pk=id, tarea__eliminado__isnull=True).select_related("alumno", "tarea__clase__modulo").first()
    if e is None:
        raise Detener(no_encontrado(request))
    if e.tarea.clase.modulo.docente_id != request.user.pk:
        raise Detener(prohibido(request))
    return e


@exigir(Rol.DOCENTE)
def calificar(request, id):
    e = _entrega_del_docente(request, id)
    desde = "tarea" if request.GET.get("desde") == "tarea" else "lista"
    penalidad = e.tardia and e.tarea.politica_tardia == PoliticaTardia.PENALIDAD
    # Si ya tenía nota y fue tardía con penalidad, mostramos la nota del trabajo (antes de restar).
    nota_previa = (e.nota + (e.tarea.penalidad_puntos if penalidad else 0)) if e.nota is not None else None
    old = request.session.get("_old", {})
    valor_nota = old.get("nota", nota_fmt(min(Decimal(20), nota_previa)) if nota_previa is not None else "")
    return vista(
        request,
        "entregas/calificar.html",
        {
            "e": e,
            "desde": desde,
            "es_imagen": e.es_imagen,
            "siguiente": e.siguiente_sin_calificar(),
            "tardia_con_penalidad": penalidad,
            "valor_nota": valor_nota,
            "comentario": old.get("comentario", e.comentario_docente),
            "criterios_puntos": [c for c in criterios_de_texto(e.tarea.criterios) if c["puntos"] is not None],
        },
        titulo=e.alumno.nombre_completo,
        sub=f"Calificar · {e.tarea.titulo}",
        volver=reverse("tareas:ver", args=[e.tarea_id]) if desde == "tarea" else reverse("tareas:por_calificar"),
        menu="calificar",
    )


@require_POST
@exigir(Rol.DOCENTE)
def guardar_nota(request, id):
    yo = request.user
    e = _entrega_del_docente(request, id)
    comentario = _entrada(request, "comentario")[:2000]
    volver = reverse("tareas:calificar", args=[id])
    nota = aprobado = None
    if e.tarea.tipo_calificacion == TipoCalificacion.APROBADO:
        v = _entrada(request, "aprobado")
        if v not in ("0", "1"):
            error(request, "Elige si aprobó o no aprobó.")
            return redirect(volver)
        aprobado = v == "1"
    else:
        try:
            nota = Decimal(_entrada(request, "nota").replace(",", "."))
        except InvalidOperation:
            nota = None
        if nota is None or not nota.is_finite() or nota < 0 or nota > 20:
            error(request, "La nota debe ser un número de 0 a 20.")
            return redirect(volver)
        # Penalidad por entrega tardía, según lo que definió el docente en la tarea.
        if e.tardia and e.tarea.politica_tardia == PoliticaTardia.PENALIDAD:
            nota = max(Decimal(0), nota - e.tarea.penalidad_puntos)
        nota = nota.quantize(Decimal("0.01"))
    if _archivo_enviado(request, "retro") is not None:
        try:
            ruta, nombre = archivos.guardar(request.FILES["retro"])
        except archivos.ArchivoError as ex:
            error(request, str(ex))
            return redirect(volver)
        anterior = e.retro_ruta
        e.retro_ruta, e.retro_nombre = ruta, nombre
        if anterior:
            archivos.borrar(anterior)
    e.nota, e.aprobado, e.comentario_docente, e.calificado = nota, aprobado, comentario, timezone.now()
    e.save()
    resultado = f": {nota_fmt(nota)}" if nota is not None else (": aprobó" if aprobado else ": no aprobó")
    Registro.anotar(
        yo,
        "notas",
        f"El docente {yo.nombre_completo} calificó «{e.tarea.titulo}» de {e.alumno.nombre_completo}{resultado}.",
        request,
    )
    Notificacion.crear(
        e.alumno,
        f"Te calificaron «{e.tarea.titulo}»" + (f": {nota_fmt(nota)}" if nota is not None else ""),
        reverse("tareas:ver", args=[e.tarea_id]),
    )
    mensaje = f"Nota de {e.alumno.primer_nombre} guardada" + (f": {nota_fmt(nota)}." if nota is not None else ".")
    desde = "tarea" if request.POST.get("desde") == "tarea" else "lista"
    siguiente = e.siguiente_sin_calificar() if request.POST.get("siguiente") == "1" else None
    ok(request, mensaje)
    if siguiente:
        return redirect(reverse("tareas:calificar", args=[siguiente.pk]) + ("?desde=tarea" if desde == "tarea" else ""))
    return redirect(reverse("tareas:ver", args=[e.tarea_id]) if desde == "tarea" else reverse("tareas:por_calificar"))


def _entrega_con_permiso(request, id):
    """La entrega, si la pide su dueño, el docente del módulo o administración/dirección."""
    u = request.user
    e = Entrega.objects.filter(pk=id, tarea__eliminado__isnull=True).select_related("tarea__clase__modulo").first()
    if e is None:
        raise Detener(no_encontrado(request))
    if u.pk not in (e.alumno_id, e.tarea.clase.modulo.docente_id) and u.rol not in (Rol.ADMIN, Rol.DIRECCION):
        raise Detener(prohibido(request))
    return e


@exigir()
def entrega_archivo(request, id):
    """Archivo entregado por el alumno: lo ve el docente del curso o el mismo alumno."""
    e = _entrega_con_permiso(request, id)
    if not e.archivo_ruta:
        return no_encontrado(request)
    return _enviar(e.archivo_ruta, e.archivo_nombre, _en_linea(e.archivo_ruta, e.archivo_nombre))


@exigir()
def entrega_retro(request, id):
    """Archivo que el docente devolvió con la nota: lo ven el alumno y el docente."""
    e = _entrega_con_permiso(request, id)
    if not e.retro_ruta:
        return no_encontrado(request)
    return _enviar(e.retro_ruta, e.retro_nombre, _en_linea(e.retro_ruta, e.retro_nombre))


calificar_o_guardar = por_metodo(GET=calificar, POST=guardar_nota)
