"""El alumno responde el formulario; el docente ve, revisa y califica."""

from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.academico.views import cargar_modulo
from apps.cuentas.models import Rol
from apps.nucleo import archivos
from apps.nucleo.models import Notificacion
from apps.nucleo.permisos import Detener, exigir, no_encontrado, prohibido
from apps.nucleo.utils import error, fecha_larga, hora_texto, nota_fmt, ok, por_metodo, vista

from . import calificar
from .models import AUTOMATICOS, CON_OPCIONES, CUADRICULAS, TOLERANCIA_MIN, Formulario, Intento, Respuesta


def _a_float(texto, defecto=0.0):
    try:
        return float(str(texto).replace(",", "."))
    except ValueError:
        return defecto


def preparar_para_responder(preguntas, previas):
    """Agrega a cada pregunta lo que la pantalla de responder necesita: su número y lo que ya respondió (si el formulario
    volvió con un error). `previas` tiene la forma de `calificar.entrada_de_post`."""
    num = 0
    for p in preguntas:
        p.num = None
        if p.es_seccion:
            continue
        num += 1
        p.num = num
        p.prev_ops = [str(x) for x in previas.get("op", {}).get(p.pk, [])]
        p.prev_txt = previas.get("txt", {}).get(p.pk, "")
        p.prev_otra = previas.get("otra", {}).get(p.pk, "")
        grid = previas.get("grid", {}).get(p.pk, {})
        p.prev_grid = {fila: [str(c) for c in cols] for fila, cols in grid.items()}
        p.es_multiple = p.tipo in ("multiple", "cuadricula_casillas")
        if p.tipo == "escala":
            p.rango = range(p.escala_min if p.escala_min is not None else 1, (p.escala_max or 5) + 1)
    return preguntas


def _cargar(request, id):
    """(intento, formulario, módulo, acceso) con los permisos verificados."""
    i = (
        Intento.objects.select_related("formulario__clase__modulo", "alumno")
        .filter(pk=id, formulario__eliminado__isnull=True)
        .first()
    )
    if i is None:
        raise Detener(no_encontrado(request))
    f = i.formulario
    modulo, acceso = cargar_modulo(request, f.clase.modulo_id)
    if acceso == "alumno" and i.alumno_id != request.user.pk:
        raise Detener(prohibido(request))
    return i, f, modulo, acceso


# ===================================================================== El alumno responde


@require_POST
@exigir(Rol.ALUMNO)
def empezar(request, id):
    f = Formulario.objects.select_related("clase__modulo").filter(pk=id).first()
    if f is None:
        return no_encontrado(request)
    cargar_modulo(request, f.clase.modulo_id)  # debe ser alumno del módulo
    u = request.user
    en_curso = Intento.objects.filter(formulario=f, alumno=u, fin__isnull=True).order_by("-id").first()
    if en_curso:
        return redirect("formularios:intento", id=en_curso.pk)
    if not f.abierto:
        error(request, "Este formulario no está disponible ahora.")
        return redirect("formularios:ver", id=id)
    if Intento.objects.filter(formulario=f, alumno=u, fin__isnull=False).count() >= f.intentos_max:
        error(request, "Ya usaste todos tus intentos.")
        return redirect("formularios:ver", id=id)
    nuevo = Intento.objects.create(formulario=f, alumno=u)
    return redirect("formularios:intento", id=nuevo.pk)


def _responder(request, i, f, modulo, previas, mensaje_error):
    """La pantalla para responder (con lo que ya escribió y un mensaje de error si hubo)."""
    preguntas = f.preguntas_completas()
    if f.mezclar:
        preguntas = calificar.mezclar(preguntas, i.pk)
        for p in preguntas:
            if p.tipo != "vf":
                p.opciones = calificar.mezclar(p.opciones, i.pk * 31 + p.pk)
    preguntas = preparar_para_responder(preguntas, previas)
    return vista(
        request,
        "formularios/responder.html",
        {
            "q": f,
            "i": i,
            "preguntas": preguntas,
            "total": sum(1 for p in preguntas if not p.es_seccion),
            "segundos": max(0, i.segundos_restantes) if f.tiempo_minutos else None,
            "error": mensaje_error,
            "vista_previa": False,
            "max_mb": settings.ARCHIVOS_MAX_MB,
        },
        titulo=f.titulo,
        sub=modulo.nombre,
        volver=None,
        menu="cursos",
    )


def _detalle_de_resultado(f, preguntas, respuestas, es_docente):
    """Agrega a cada pregunta cómo se muestra su respuesta en la pantalla de resultados."""
    nombres = {o.pk: o.texto for p in preguntas for o in [*p.opciones, *p.filas, *p.columnas]}
    num = 0
    hay_revisables = False
    for p in preguntas:
        p.num = None
        if p.es_seccion:
            continue
        num += 1
        p.num = num
        r = respuestas.get(p.pk)
        p.r = r
        marcadas = r.ids_marcados if r else []
        pts = r.puntos if r else None
        p.con_puntos = f.es_examen and float(p.puntos) > 0
        p.bien = pts is not None and float(pts) >= float(p.puntos)
        p.tiene_algo = bool(r and r.tiene_algo)
        p.revisar_esta = bool(
            es_docente
            and p.con_puntos
            and p.tiene_algo
            and (p.tipo not in AUTOMATICOS or (p.tipo == "corta" and not p.respuestas_aceptadas))
        )
        hay_revisables = hay_revisables or p.revisar_esta
        p.estado_puntos = ""
        if p.con_puntos:
            if pts is None:
                p.chip_estado, p.estado_puntos = "chip-gris", "Por revisar"
            else:
                p.chip_estado = "chip-ok" if p.bien else ("chip-aviso" if float(pts) > 0 else "chip-mal")
                p.estado_puntos = (
                    f"{'Bien' if p.bien else ('En parte' if float(pts) > 0 else 'Mal')} · {nota_fmt(pts)} de {nota_fmt(p.puntos)}"
                )
        p.puntos_valor = nota_fmt(pts) if pts is not None else ""
        if p.tipo in CON_OPCIONES or p.tipo == "vf":
            filas = []
            for k, o in enumerate(p.opciones):
                mia = o.pk in marcadas
                es_correcta = f.es_examen and o.correcta
                if p.tipo == "desplegable" and not mia and not es_correcta:
                    continue
                clases = " ".join(
                    c
                    for c in (
                        "es-correcta" if es_correcta else "",
                        "es-error" if mia and f.es_examen and not es_correcta and p.con_puntos else "",
                        "es-elegida" if mia and not f.es_examen else "",
                    )
                    if c
                )
                filas.append(
                    {
                        "o": o,
                        "k": k,
                        "mia": mia,
                        "correcta": es_correcta,
                        "clases": clases,
                        "icono": "check" if (es_correcta or not f.es_examen) else "alerta",
                    }
                )
            p.filas_resultado = filas
            p.otra_texto = r.texto if r and r.texto else ""
        elif p.tipo in CUADRICULAS:
            grid = calificar.grid_de(r) if r else {}
            p.filas_grid = [(fila.texto, [nombres.get(c, "") for c in grid.get(fila.pk, [])]) for fila in p.filas]
        elif p.tipo != "archivo":
            p.texto_mostrado = _texto_para_mostrar(p, r.texto if r and r.texto else None)
    return hay_revisables


def _texto_para_mostrar(p, texto):
    """Una respuesta escrita, como se lee mejor: la fecha y la hora en palabras, la escala con su rango."""
    if not texto:
        return None
    try:
        if p.tipo == "fecha":
            d = datetime.strptime(texto, "%Y-%m-%d")
            larga = fecha_larga(d)
            return f"{larga[:1].upper()}{larga[1:]} de {d.year}"
        if p.tipo == "hora":
            return hora_texto(datetime.strptime("2000-01-01 " + texto, "%Y-%m-%d %H:%M"))
    except ValueError:
        return texto
    if p.tipo == "escala":
        return f"{texto} (de {p.escala_min} a {p.escala_max})"
    return texto


@exigir()
def intento(request, id):
    """Alumno: responder (si sigue abierto) o ver sus respuestas. Docente: ver y revisar las respuestas."""
    i, f, modulo, acceso = _cargar(request, id)
    u = request.user
    pagina = {"titulo": f.titulo, "sub": modulo.nombre, "volver": reverse("formularios:ver", args=[f.pk]), "menu": "cursos"}

    if acceso == "alumno":
        if i.fin is None:
            if i.segundos_restantes < -60 * TOLERANCIA_MIN:
                # Se acabó el tiempo y no envió: se cierra con lo que haya (en blanco).
                calificar.entregar(i, f, f.preguntas_completas(), {})
                error(request, "Se acabó el tiempo.")
                return redirect("formularios:intento", id=id)
            return _responder(request, i, f, modulo, {}, None)
        return _resultado(
            request,
            i,
            f,
            modulo,
            False,
            max(0, f.intentos_max - Intento.objects.filter(formulario=f, alumno=u, fin__isnull=False).count()),
            pagina,
        )

    if i.fin is None:
        error(request, "Ese alumno todavía está respondiendo.")
        return redirect(reverse("formularios:resultados", args=[f.pk]) + "?ver=personas")
    return _resultado(
        request,
        i,
        f,
        modulo,
        acceso == "docente",
        0,
        {
            "titulo": i.alumno.nombre_completo,
            "sub": f.titulo,
            "volver": reverse("formularios:resultados", args=[f.pk]) + "?ver=personas",
            "menu": "cursos",
        },
    )


def _resultado(request, i, f, modulo, es_docente, quedan, pagina):
    preguntas = f.preguntas_completas()
    respuestas = i.respuestas_por_pregunta()
    hay_revisables = _detalle_de_resultado(f, preguntas, respuestas, es_docente)
    es_alumno = request.user.rol == Rol.ALUMNO
    ver_detalle = es_docente or f.mostrar_respuestas or not es_alumno
    return vista(
        request,
        "formularios/resultado.html",
        {
            "q": f,
            "i": i,
            "preguntas": preguntas,
            "es_docente": es_docente,
            "es_alumno": es_alumno,
            "quedan": quedan,
            "ver_detalle": ver_detalle,
            "hay_revisables": hay_revisables,
            "aprobo": i.nota is not None and float(i.nota) >= 11,
            "nota_texto": nota_fmt(i.nota) if i.nota is not None else "",
            "puntaje_texto": nota_fmt(i.puntaje),
            "puntaje_max_texto": nota_fmt(i.puntaje_max),
            "mensaje_final": f.mensaje_final or "¡Gracias! Tus respuestas se guardaron.",
        },
        **pagina,
    )


@require_POST
@exigir()
def entregar(request, id):
    i, f, modulo, acceso = _cargar(request, id)
    if acceso != "alumno":
        return prohibido(request)
    if i.fin is not None:
        error(request, "Este formulario ya fue enviado.")
        return redirect("formularios:intento", id=id)
    preguntas = f.preguntas_completas()
    entrada = calificar.entrada_de_post(request.POST)
    tiempo_acabado = i.segundos_restantes <= 10

    # Preguntas obligatorias: si falta alguna, vuelve a mostrar el formulario con lo que ya respondió.
    enviados = {}
    for p in preguntas:
        if p.tipo == "archivo":
            subido = request.FILES.get(f"archivo_{p.pk}")
            if subido is not None and subido.size > 0:
                enviados[p.pk] = ("", "")
    faltan = calificar.faltantes(preguntas, entrada, enviados)
    if faltan and not tiempo_acabado:
        msg = (
            f"Falta responder la pregunta {faltan[0]}."
            if len(faltan) == 1
            else "Faltan responder las preguntas " + ", ".join(str(n) for n in faltan) + "."
        )
        return _responder(request, i, f, modulo, entrada, msg + (" Vuelve a elegir tus archivos." if enviados else ""))

    # Archivos que subió el alumno
    guardados = {}
    for pid in enviados:
        try:
            guardados[pid] = archivos.guardar(request.FILES[f"archivo_{pid}"])
        except archivos.ArchivoError as ex:
            for ruta, _nombre in guardados.values():
                archivos.borrar(ruta)
            return _responder(request, i, f, modulo, entrada, f"{ex} Vuelve a elegir tus archivos.")
    calificar.entregar(i, f, preguntas, entrada, guardados)
    ok(request, f.mensaje_final or "¡Enviado! Tus respuestas se guardaron.")
    return redirect("formularios:intento", id=id)


# ===================================================================== El docente revisa


@require_POST
@exigir(Rol.DOCENTE)
def revisar(request, id):
    """El docente revisa: puntos por pregunta (examen) o una nota para todo (trabajo)."""
    i, f, modulo, acceso = _cargar(request, id)
    if acceso != "docente":
        return prohibido(request)
    volver = reverse("formularios:intento", args=[id])
    general = (request.POST.get("comentario_general") or "").strip()[:2000]
    if f.modo == "trabajo":
        texto = (request.POST.get("nota") or "").strip().replace(",", ".")
        try:
            nota = float(texto)
        except ValueError:
            nota = -1
        if nota < 0 or nota > 20:
            error(request, "La nota debe ser un número de 0 a 20.")
            return redirect(volver)
        calificar.calificar_trabajo(i, nota, general)
    else:
        puntos, comentarios = {}, {}
        for p in f.preguntas.all():
            crudo = (request.POST.get(f"puntos[{p.pk}]") or "").strip()
            if crudo == "":
                continue
            v = _a_float(crudo)
            if v < 0 or v > float(p.puntos):
                error(request, f"Los puntos de cada pregunta van de 0 a {nota_fmt(p.puntos)}.")
                return redirect(volver)
            puntos[p.pk] = Decimal(str(round(v, 2)))
            comentarios[p.pk] = (request.POST.get(f"comentario[{p.pk}]") or "").strip()[:500]
        calificar.revisar(i, puntos, comentarios, general)
    Notificacion.crear(i.alumno, f"Tu profesor revisó: {f.titulo}", reverse("formularios:intento", args=[id]))
    siguientes = [x for x in por_revisar(request.user) if x.pk != i.pk]
    mensaje = f"Revisión guardada de {i.alumno.primer_nombre}."
    ok(request, mensaje)
    if request.POST.get("siguiente") == "1" and siguientes:
        return redirect("formularios:intento", id=siguientes[0].pk)
    return redirect(reverse("formularios:resultados", args=[f.pk]) + "?ver=personas")


def por_revisar(docente):
    """Formularios terminados que esperan la revisión del docente (el más antiguo primero)."""
    return list(
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


@exigir()
def archivo_de_respuesta(request, id):
    """Archivo que subió el alumno en una pregunta (lo ven él, su docente y administración)."""
    r = (
        Respuesta.objects.filter(pk=id, intento__formulario__eliminado__isnull=True)
        .select_related("intento__formulario__clase__modulo")
        .first()
    )
    if r is None:
        return no_encontrado(request)
    u = request.user
    modulo = r.intento.formulario.clase.modulo
    if u.pk not in (r.intento.alumno_id, modulo.docente_id) and u.rol not in (Rol.ADMIN, Rol.DIRECCION):
        return prohibido(request)
    if not r.archivo_ruta:
        return no_encontrado(request)
    en_linea = archivos.es_imagen(r.archivo_ruta) or r.archivo_nombre.lower().endswith(".pdf")
    return archivos.enviar(r.archivo_ruta, r.archivo_nombre, en_linea=en_linea)


intento_o_entregar = por_metodo(GET=intento, POST=entregar)
