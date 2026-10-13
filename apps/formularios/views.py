"""Formularios (examen, trabajo o encuesta): el docente los arma y publica; el alumno ve la portada y empieza.
Mismas pantallas y direcciones que el sistema anterior (/examenes/…, /preguntas/…)."""

import csv
import re
from datetime import datetime, timedelta

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from apps.academico.models import Clase
from apps.academico.views import cargar_modulo, modulo_del_docente
from apps.cuentas.models import Rol
from apps.nucleo import archivos
from apps.nucleo.models import Notificacion
from apps.nucleo.permisos import Detener, exigir, no_encontrado, prohibido
from apps.nucleo.utils import csv_fila, error, fecha_larga, hora_texto, nota_fmt, ok, por_metodo, vista, volver_con_error

from . import calificar
from .models import CON_OPCIONES, GRUPOS_DE_TIPOS, MODOS, TIPOS, Formulario, Intento, Pregunta
from .views_intentos import preparar_para_responder

TIEMPOS = [
    ("0", "Sin límite"), ("10", "10 minutos"), ("15", "15 minutos"), ("20", "20 minutos"), ("30", "30 minutos"),
    ("45", "45 minutos"), ("60", "1 hora"), ("90", "1 hora y media"), ("120", "2 horas"),
]  # fmt: skip
INTENTOS = [1, 2, 3, 5]


def _entrada(request, clave, defecto=""):
    return (request.POST.get(clave) or defecto).strip()


def _a_float(texto, defecto=0.0):
    try:
        return float(str(texto).replace(",", "."))
    except ValueError:
        return defecto


def _formulario(request, id):
    """(formulario, módulo, acceso) con los permisos verificados."""
    f = Formulario.objects.select_related("clase__modulo").filter(pk=id).first()
    if f is None:
        raise Detener(no_encontrado(request))
    modulo, acceso = cargar_modulo(request, f.clase.modulo_id)
    return f, modulo, acceso


def _del_docente(request, id):
    """(formulario, módulo): solo el docente del módulo."""
    f = Formulario.objects.select_related("clase__modulo").filter(pk=id).first()
    if f is None:
        raise Detener(no_encontrado(request))
    return f, modulo_del_docente(request, f.clase.modulo_id)


def _editable(request, id):
    """(formulario, módulo): solo el docente, y mientras ningún alumno haya respondido."""
    f, modulo = _del_docente(request, id)
    if f.hay_intentos():
        error(request, "Ya hay alumnos que respondieron: no se pueden cambiar las preguntas.")
        raise Detener(redirect("formularios:ver", id=f.pk))
    return f, modulo


def _pregunta_editable(request, id):
    """(pregunta con sus alternativas, formulario, módulo)"""
    p = Pregunta.objects.filter(pk=id, formulario__eliminado__isnull=True).first()
    if p is None:
        raise Detener(no_encontrado(request))
    f, modulo = _editable(request, p.formulario_id)
    return p.cargar_opciones(), f, modulo


def _clases_numeradas(modulo):
    clases = list(modulo.clases.all())
    for n, c in enumerate(clases, start=1):
        c.n = n
    return clases


# ===================================================================== Crear y cambiar el formulario


def _datos_del_formulario(request, modulo, volver):
    """Lee y revisa los datos del formulario. Si algo está mal, vuelve al formulario con el mensaje."""
    titulo = _entrada(request, "titulo")[:150]
    modo = _entrada(request, "modo", "examen")
    try:
        limite = timezone.make_aware(
            datetime.strptime(f"{_entrada(request, 'fecha')} {_entrada(request, 'hora', '23:59')}", "%Y-%m-%d %H:%M")
        )
    except ValueError:
        limite = None
    inicio = None
    if _entrada(request, "desde_fecha"):
        try:
            inicio = timezone.make_aware(
                datetime.strptime(
                    f"{_entrada(request, 'desde_fecha')} {_entrada(request, 'desde_hora', '00:00')}", "%Y-%m-%d %H:%M"
                )
            )
        except ValueError:
            raise Detener(volver_con_error(request, volver, "La fecha «desde» no es válida.")) from None
    if titulo == "":
        raise Detener(volver_con_error(request, volver, "Escribe el nombre del formulario."))
    if modo not in MODOS:
        raise Detener(volver_con_error(request, volver, "Elige si es examen, trabajo o encuesta."))
    if limite is None:
        raise Detener(volver_con_error(request, volver, "Elige hasta qué día se puede responder."))
    if inicio and inicio >= limite:
        raise Detener(volver_con_error(request, volver, "La fecha «desde» debe ser antes de la fecha límite."))
    clase_id = _entrada(request, "unidad_id")
    clase = Clase.objects.filter(pk=clase_id, modulo=modulo).first() if clase_id.isdigit() else None
    if clase is None:
        clase = Clase.ultima_o_crear(modulo)
    tiempo = int(_entrada(request, "tiempo_minutos", "0")) if _entrada(request, "tiempo_minutos", "0").isdigit() else 0
    intentos = int(_entrada(request, "intentos_max", "1")) if _entrada(request, "intentos_max", "1").isdigit() else 1
    return {
        "clase": clase,
        "modo": modo,
        "titulo": titulo,
        "instrucciones": _entrada(request, "instrucciones")[:3000],
        "mensaje_final": _entrada(request, "mensaje_final")[:500],
        "fecha_inicio": inicio,
        "fecha_limite": limite,
        "tiempo_minutos": min(tiempo, 300) if tiempo > 0 else None,
        "intentos_max": max(1, min(5, intentos)),
        "mezclar": "mezclar" in request.POST,
        "mostrar_respuestas": "mostrar_respuestas" in request.POST,
    }


def _contexto_form(request, modulo, f, modo_defecto, clase_elegida, fecha_defecto):
    """Valores del formulario: lo escrito si volvió con un error; si no, lo guardado (o lo de por defecto)."""
    old = request.session.get("_old", {})
    clases = _clases_numeradas(modulo)
    lim = timezone.localtime(f.fecha_limite) if f else None
    desde = timezone.localtime(f.fecha_inicio) if f and f.fecha_inicio else None

    def val(campo, defecto=""):
        return old.get(campo, defecto)

    actual = Clase.actual(clases)
    valores = {
        "modo": val("modo", modo_defecto),
        "titulo": val("titulo", f.titulo if f else ""),
        "instrucciones": val("instrucciones", f.instrucciones if f else ""),
        "fecha": val("fecha", lim.strftime("%Y-%m-%d") if lim else fecha_defecto),
        "hora": val("hora", lim.strftime("%H:%M") if lim else "23:59"),
        "tiempo": val("tiempo_minutos", str(f.tiempo_minutos or 0) if f else "0"),
        "intentos": val("intentos_max", str(f.intentos_max) if f else "1"),
        "desde_fecha": val("desde_fecha", desde.strftime("%Y-%m-%d") if desde else ""),
        "desde_hora": val("desde_hora", desde.strftime("%H:%M") if desde else "08:00"),
        "mensaje_final": val("mensaje_final", f.mensaje_final if f else ""),
        "unidad": val("unidad_id", str(f.clase_id) if f else (clase_elegida or (str(actual.pk) if actual else ""))),
        "mezclar": ("mezclar" in old) if old else bool(f and f.mezclar),
        "mostrar_respuestas": ("mostrar_respuestas" in old) if old else (f.mostrar_respuestas if f else True),
    }
    return {
        "modulo": modulo,
        "q": f,
        "v": valores,
        "modos": [(k, v[0], v[1]) for k, v in MODOS.items()],
        "tiempos": TIEMPOS,
        "intentos_lista": [(str(k), "1 intento" if k == 1 else f"{k} intentos (vale la mejor nota)") for k in INTENTOS],
        "clases": clases,
        "abrir_mas": bool(desde) or bool(f and len(clases) > 1),
        "accion": reverse("formularios:editar", args=[f.pk]) if f else reverse("formularios:guardar", args=[modulo.pk]),
    }


@exigir(Rol.DOCENTE)
def nuevo(request, id):
    modulo = modulo_del_docente(request, id)
    modo = request.GET.get("modo", "")
    clase_id = request.GET.get("clase", "")
    clase = Clase.objects.filter(pk=clase_id, modulo=modulo).first() if clase_id.isdigit() else None
    return vista(
        request,
        "formularios/form.html",
        _contexto_form(
            request,
            modulo,
            None,
            modo if modo in MODOS else "examen",
            str(clase.pk) if clase else "",
            (timezone.localdate() + timedelta(days=7)).isoformat(),
        ),
        titulo="Nuevo formulario",
        sub=f"Clase: {clase.titulo}" if clase else modulo.nombre,
        volver=(reverse("academico:clase", args=[clase.pk]) + "#crear") if clase else reverse("tareas:modulo", args=[id]),
        menu="cursos",
    )


@require_POST
@exigir(Rol.DOCENTE)
def guardar(request, id):
    modulo = modulo_del_docente(request, id)
    datos = _datos_del_formulario(request, modulo, reverse("formularios:nuevo", args=[id]))
    f = Formulario.objects.create(**datos)
    ok(request, "Formulario creado. Ahora agrega las preguntas.")
    return redirect(reverse("formularios:ver", args=[f.pk]) + "#nueva")


@exigir(Rol.DOCENTE)
def editar(request, id):
    f, modulo = _del_docente(request, id)
    return vista(
        request,
        "formularios/form.html",
        _contexto_form(request, modulo, f, f.modo, "", ""),
        titulo="Datos del formulario",
        sub=f.titulo,
        volver=reverse("formularios:ver", args=[id]),
        menu="cursos",
    )


@require_POST
@exigir(Rol.DOCENTE)
def actualizar(request, id):
    f, modulo = _del_docente(request, id)
    volver = reverse("formularios:editar", args=[id])
    datos = _datos_del_formulario(request, modulo, volver)
    if datos["modo"] != f.modo and f.hay_intentos():
        return volver_con_error(request, volver, "Ya hay respuestas: no se puede cambiar si es examen, trabajo o encuesta.")
    for campo, valor in datos.items():
        setattr(f, campo, valor)
    f.save()
    ok(request, "Cambios guardados.")
    return redirect("formularios:ver", id=id)


@require_POST
@exigir(Rol.DOCENTE)
def publicar(request, id):
    f, modulo = _del_docente(request, id)
    publicar_ = request.POST.get("publicar") == "1"
    if publicar_ and not f.preguntas.exclude(tipo="seccion").exists():
        error(request, "Agrega al menos una pregunta antes de publicar.")
        return redirect("formularios:ver", id=id)
    era_publico = f.publicado
    f.publicado = publicar_
    f.save(update_fields=["publicado"])
    if publicar_ and not era_publico and f.clase.situacion != "proxima":
        Notificacion.a_alumnos(modulo, f"Nuevo formulario para responder: {f.titulo}", reverse("formularios:ver", args=[id]))
    ok(request, "¡Publicado! Tus alumnos ya lo ven en su Inicio." if publicar_ else "Oculto. Tus alumnos ya no lo ven.")
    return redirect("formularios:ver", id=id)


@require_POST
@exigir(Rol.DOCENTE)
def eliminar(request, id):
    f, _modulo = _del_docente(request, id)
    f.eliminado = timezone.now()  # va a la papelera con sus respuestas; se borra de verdad a los 30 días
    f.save(update_fields=["eliminado"])
    ok(request, "Formulario enviado a la papelera. Puedes recuperarlo durante 30 días.")
    return redirect("academico:clase", id=f.clase_id)


# ===================================================================== Ver: el docente arma, el alumno ve la portada


@exigir()
def ver(request, id):
    """Docente: armar preguntas. Alumno: portada del formulario."""
    f, modulo, acceso = _formulario(request, id)
    u = request.user
    pagina = {"titulo": f.titulo, "sub": modulo.nombre, "volver": reverse("tareas:modulo", args=[modulo.pk]), "menu": "cursos"}

    if acceso == "alumno":
        if not f.publicado or f.de_clase_proxima or not f.clase.visible:
            return no_encontrado(request)
        if request.GET.get("desde") == "inicio":
            pagina.update(volver=reverse("nucleo:inicio"), menu="inicio")
        hechos = list(Intento.objects.filter(formulario=f, alumno=u, fin__isnull=False).order_by("id"))
        notas = [float(i.nota) for i in hechos if i.revisado and i.nota is not None]
        mejor = max(notas) if notas else None
        for h in hechos:
            h.nota_texto = nota_fmt(h.nota) if h.nota is not None else ""
        if f.vencido:
            mensaje_cerrado = "La fecha ya pasó."
        elif f.fecha_inicio and f.fecha_inicio > timezone.now():
            mensaje_cerrado = (
                f"Todavía no se puede responder. Se abre el {fecha_larga(f.fecha_inicio)} a las {hora_texto(f.fecha_inicio)}."
            )
        else:
            mensaje_cerrado = "Este formulario no está disponible ahora."
        return vista(
            request,
            "formularios/portada.html",
            {
                "q": f,
                "hechos": hechos,
                "en_curso": Intento.objects.filter(formulario=f, alumno=u, fin__isnull=True).order_by("-id").first(),
                "abierto": f.abierto,
                "quedan": max(0, f.intentos_max - len(hechos)),
                "mejor": mejor,
                "aprobo": mejor is not None and mejor >= 11,
                "por_revisar": sum(1 for h in hechos if not h.revisado),
                "cosa": {"examen": "el examen", "trabajo": "el trabajo", "encuesta": "la encuesta"}[f.modo],
                "total_preguntas": f.preguntas.exclude(tipo="seccion").count(),
                "mensaje_cerrado": mensaje_cerrado,
            },
            **pagina,
        )

    preguntas = f.preguntas_completas()
    aciertos = calificar.aciertos_por_pregunta(f)
    num = 0
    for p in preguntas:
        if not p.es_seccion:
            num += 1
        p.num = None if p.es_seccion else num
        p.pct = aciertos.get(p.pk)
    f.total_preguntas, f.total_puntos = num, sum(float(p.puntos) for p in preguntas if not p.es_seccion)
    bloqueado = f.hay_intentos()
    es_docente = acceso == "docente"
    old = request.session.get("_old", {})
    return vista(
        request,
        "formularios/editor.html",
        {
            "q": f,
            "modulo": modulo,
            "acceso": acceso,
            "es_docente": es_docente,
            "es_examen": f.es_examen,
            "preguntas": preguntas,
            "bloqueado": bloqueado,
            "editable": es_docente and not bloqueado,
            "siguiente_numero": num + 1,
            **(_contexto_pregunta(f, None, old) if es_docente and not bloqueado else {}),
        },
        **pagina,
    )


@exigir()
def vista_previa(request, id):
    """El docente ve el formulario como lo verá el alumno (sin poder enviarlo)."""
    f, modulo, acceso = _formulario(request, id)
    if acceso == "alumno":
        return prohibido(request)
    preguntas = preparar_para_responder(f.preguntas_completas(), {})
    return vista(
        request,
        "formularios/responder.html",
        {
            "q": f,
            "i": None,
            "preguntas": preguntas,
            "total": sum(1 for p in preguntas if not p.es_seccion),
            "segundos": None,
            "error": None,
            "vista_previa": True,
            "max_mb": settings.ARCHIVOS_MAX_MB,
        },
        titulo=f.titulo,
        sub="Vista previa",
        volver=reverse("formularios:ver", args=[id]),
        menu="cursos",
    )


# ===================================================================== Preguntas


def _contexto_pregunta(f, p, old):
    """Lo que necesita el formulario de una pregunta (agregar o cambiar)."""
    tipo = old.get("tipo") or (p.tipo if p else "opcion")
    opciones = p.opciones if p and p.tipo in CON_OPCIONES else []
    n_filas = max(3, len(opciones) + 1)
    vf_correcta = ""
    if p and p.tipo == "vf":
        for o in p.opciones:
            if o.correcta:
                vf_correcta = "v" if o.texto == "Verdadero" else "f"
    return {
        "fp": {
            "q": f,
            "p": p,
            "uid": f"e{p.pk}" if p else "n",
            "tipo": tipo,
            "grupos": [(g, [(t, TIPOS[t][0]) for t in tipos]) for g, tipos in GRUPOS_DE_TIPOS],
            "filas_opcion": [(i, opciones[i] if i < len(opciones) else None) for i in range(n_filas)],
            "vf_correcta": vf_correcta,
            "obligatoria": p.obligatoria if p else True,
            "enunciado": old.get("enunciado", p.enunciado if p else ""),
            "ayuda": old.get("ayuda", p.ayuda if p else ""),
            "puntos": old.get("puntos", nota_fmt(p.puntos) if p else "2"),
            "escala_min": str(p.escala_min if p and p.escala_min is not None else 1),
            "escala_max": p.escala_max if p and p.escala_max else 5,
            "escala_maximos": range(2, 11),
            "filas_cuadricula": "\n".join(o.texto for o in (p.filas if p else [])),
            "columnas_cuadricula": "\n".join(o.texto for o in (p.columnas if p else [])),
        }
    }


def _datos_de_pregunta(request, f, actual, volver):
    """Lee y revisa una pregunta del formulario. `actual` = la pregunta que se está cambiando (o None)."""
    es_examen = f.es_examen
    tipo = _entrada(request, "tipo")
    if tipo not in TIPOS:
        raise Detener(volver_con_error(request, volver, "Elige el tipo de pregunta."))
    enunciado = _entrada(request, "enunciado")[:3000]
    if enunciado == "":
        raise Detener(volver_con_error(request, volver, "Escribe el título." if tipo == "seccion" else "Escribe la pregunta."))
    puntos = 0.0
    if es_examen and tipo != "seccion":
        puntos = _a_float(_entrada(request, "puntos", "1"))
        if puntos < 0 or puntos > 100:
            raise Detener(volver_con_error(request, volver, "Los puntos deben ser un número de 0 a 100."))
    d = {
        "tipo": tipo,
        "enunciado": enunciado,
        "ayuda": _entrada(request, "ayuda")[:500],
        "imagen_ruta": actual.imagen_ruta if actual else "",
        "obligatoria": tipo != "seccion" and "obligatoria" in request.POST,
        "puntos": round(puntos, 2),
        "aceptadas": "",
        "explicacion": _entrada(request, "explicacion")[:2000] if es_examen else "",
        "permite_otra": False,
        "escala_min": None,
        "escala_max": None,
        "etiqueta_min": "",
        "etiqueta_max": "",
        "opciones": [],
    }

    if tipo in CON_OPCIONES:
        textos = {}
        for clave in request.POST:
            m = re.fullmatch(r"opcion\[(\d+)\]", clave)
            if m:
                textos[int(m.group(1))] = request.POST[clave]
        marcadas = set(request.POST.getlist("correctas[]"))
        for i in sorted(textos):
            texto = textos[i].strip()[:500]
            if texto:
                d["opciones"].append([texto, es_examen and str(i) in marcadas, "opcion"])
        n_correctas = sum(1 for o in d["opciones"] if o[1])
        if len(d["opciones"]) < 2:
            raise Detener(volver_con_error(request, volver, "Escribe al menos 2 opciones."))
        if es_examen and puntos > 0 and tipo != "multiple" and n_correctas != 1:
            raise Detener(volver_con_error(request, volver, "Marca cuál es la opción correcta (solo una)."))
        if es_examen and puntos > 0 and tipo == "multiple" and n_correctas < 1:
            raise Detener(volver_con_error(request, volver, "Marca las opciones correctas."))
        d["permite_otra"] = tipo != "desplegable" and "permite_otra" in request.POST
    elif tipo == "vf":
        v = _entrada(request, "vf_correcta")
        if es_examen and puntos > 0 and v not in ("v", "f"):
            raise Detener(volver_con_error(request, volver, "Elige si la respuesta correcta es Verdadero o Falso."))
        d["opciones"] = [["Verdadero", es_examen and v == "v", "opcion"], ["Falso", es_examen and v == "f", "opcion"]]
    elif tipo == "corta" and es_examen:
        lineas = [x.strip() for x in _entrada(request, "aceptadas").splitlines() if x.strip()]
        d["aceptadas"] = "\n".join(lineas)[:2000]
    elif tipo == "escala":
        d["escala_min"] = 0 if _entrada(request, "escala_min", "1") == "0" else 1
        maximo = _entrada(request, "escala_max", "5")
        d["escala_max"] = max(2, min(10, int(maximo) if maximo.isdigit() else 5))
        d["etiqueta_min"] = _entrada(request, "etiqueta_min")[:60]
        d["etiqueta_max"] = _entrada(request, "etiqueta_max")[:60]
    elif tipo in ("cuadricula", "cuadricula_casillas"):
        filas = [x.strip() for x in _entrada(request, "filas").splitlines() if x.strip()][:20]
        cols = [x.strip() for x in _entrada(request, "columnas").splitlines() if x.strip()][:10]
        if not filas or len(cols) < 2:
            raise Detener(volver_con_error(request, volver, "Escribe al menos 1 fila y 2 columnas (una por línea)."))
        d["opciones"] = [[x[:500], False, "fila"] for x in filas] + [[x[:500], False, "columna"] for x in cols]

    # Imagen opcional de la pregunta
    if "quitar_imagen" in request.POST:
        d["imagen_ruta"] = ""
    subida = request.FILES.get("imagen")
    if subida is not None and subida.size > 0:
        extension = subida.name.rsplit(".", 1)[-1].lower() if "." in subida.name else ""
        if extension not in archivos.IMAGENES:
            raise Detener(volver_con_error(request, volver, "La imagen debe ser una foto (JPG, PNG o WEBP)."))
        try:
            d["imagen_ruta"] = archivos.guardar(subida)[0]
        except archivos.ArchivoError as ex:
            raise Detener(volver_con_error(request, volver, str(ex))) from ex
    return d


@require_POST
@exigir(Rol.DOCENTE)
def agregar_pregunta(request, id):
    f, _modulo = _editable(request, id)
    d = _datos_de_pregunta(request, f, None, reverse("formularios:ver", args=[id]) + "#nueva")
    p = Pregunta.guardar(f, None, d)
    ok(request, "Título agregado." if d["tipo"] == "seccion" else "Pregunta agregada. Para otra, toca «+ Agregar pregunta».")
    return redirect(reverse("formularios:ver", args=[id]) + f"#p{p.pk}")


@exigir(Rol.DOCENTE)
def editar_pregunta(request, id):
    p, f, _modulo = _pregunta_editable(request, id)
    old = request.session.get("_old", {})
    return vista(
        request,
        "formularios/pregunta.html",
        {
            "q": f,
            **_contexto_pregunta(f, p, old),
            "accion": reverse("formularios:pregunta_actualizar", args=[p.pk]),
            "boton": "Guardar cambios",
        },
        titulo="Cambiar pregunta",
        sub=f.titulo,
        volver=reverse("formularios:ver", args=[f.pk]) + f"#p{p.pk}",
        menu="cursos",
    )


@require_POST
@exigir(Rol.DOCENTE)
def actualizar_pregunta(request, id):
    p, f, _modulo = _pregunta_editable(request, id)
    d = _datos_de_pregunta(request, f, p, reverse("formularios:pregunta_editar", args=[id]))
    Pregunta.guardar(f, p, d)
    ok(request, "Pregunta guardada.")
    return redirect(reverse("formularios:ver", args=[f.pk]) + f"#p{id}")


@require_POST
@exigir(Rol.DOCENTE)
def duplicar_pregunta(request, id):
    p, f, _modulo = _pregunta_editable(request, id)
    nueva = p.duplicar()
    ok(request, "Pregunta copiada. Cámbiala con «Cambiar».")
    return redirect(reverse("formularios:ver", args=[f.pk]) + f"#p{nueva.pk}")


@require_POST
@exigir(Rol.DOCENTE)
def eliminar_pregunta(request, id):
    p, f, _modulo = _pregunta_editable(request, id)
    p.delete()  # la imagen de la pregunta se borra con ella
    ok(request, "Pregunta borrada.")
    return redirect("formularios:ver", id=f.pk)


@require_POST
@exigir(Rol.DOCENTE)
def mover_pregunta(request, id):
    p, f, _modulo = _pregunta_editable(request, id)
    p.mover(request.POST.get("dir") == "arriba")
    return redirect(reverse("formularios:ver", args=[f.pk]) + f"#p{id}")


@exigir()
def imagen_de_pregunta(request, id):
    """Imagen de una pregunta (la ven el docente y los alumnos del módulo)."""
    p = Pregunta.objects.filter(pk=id, formulario__eliminado__isnull=True).select_related("formulario__clase").first()
    if p is None:
        return no_encontrado(request)
    _modulo, acceso = cargar_modulo(request, p.formulario.clase.modulo_id)
    if acceso == "alumno" and (not p.formulario.publicado or p.formulario.de_clase_proxima):
        return no_encontrado(request)
    if not p.imagen_ruta:
        return no_encontrado(request)
    extension = p.imagen_ruta.rsplit(".", 1)[-1]
    return archivos.enviar(p.imagen_ruta, f"imagen-pregunta-{p.pk}.{extension}", en_linea=True)


# ===================================================================== Respuestas


@exigir()
def resultados(request, id):
    f, modulo, acceso = _formulario(request, id)
    if acceso == "alumno":
        return prohibido(request)
    preguntas = f.preguntas_completas()
    filas = calificar.resultados(f, modulo)
    notas = [x["mejor_nota"] for x in filas if x["mejor_nota"] is not None]
    for x in filas:
        if x["por_revisar"] and x["mejor_nota"] is None:
            x["chip"], x["texto"] = "chip-aviso", "Por revisar"
        elif x["mejor_nota"] is not None:
            x["chip"], x["texto"] = ("chip-ok" if x["mejor_nota"] >= 11 else "chip-mal"), f"Nota {nota_fmt(x['mejor_nota'])}"
        elif x["intento_id"] is not None:
            x["chip"], x["texto"] = "chip-ok", "Respondió"
        else:
            x["chip"], x["texto"] = "chip-gris", "No respondió"
    num = 0
    resumen = calificar.resumen(f, preguntas)
    for p in preguntas:
        if not p.es_seccion:
            num += 1
        p.num = None if p.es_seccion else num
        p.resumen = resumen.get(p.pk, {"total": 0, "conteo": {}, "otras": [], "textos": [], "grid": {}})
        _preparar_resumen(f, p)
    ver_ = "personas" if request.GET.get("ver") == "personas" else "resumen"
    base = reverse("formularios:resultados", args=[id])
    return vista(
        request,
        "formularios/resultados.html",
        {
            "q": f,
            "acceso": acceso,
            "filas": filas,
            "dieron": sum(1 for x in filas if x["intentos"] > 0),
            "total_alumnos": len(filas),
            "promedio": calificar.redondear(sum(notas) / len(notas), 1) if notas else None,
            "aprobados": sum(1 for n in notas if n >= 11),
            "con_nota": not f.es_encuesta,
            "preguntas": preguntas,
            "ver": ver_,
            "base": base,
        },
        titulo="Respuestas",
        sub=f.titulo,
        volver=reverse("formularios:ver", args=[id]),
        menu="cursos",
    )


def _preparar_resumen(f, p):
    """Agrega a la pregunta lo que necesita la pantalla de respuestas: barras de cada alternativa o la tabla de la cuadrícula."""
    s = p.resumen
    p.barras = []
    if p.tipo == "escala":
        for n in range(p.escala_min if p.escala_min is not None else 1, (p.escala_max or 5) + 1):
            p.barras.append((str(n), s["conteo"].get(n, 0), False))
    elif p.tipo in ("opcion", "multiple", "desplegable", "vf"):
        for o in p.opciones:
            p.barras.append((o.texto, s["conteo"].get(o.pk, 0), f.es_examen and o.correcta))
        if p.permite_otra:
            p.barras.append(("Otra", len(s["otras"]), False))
    p.barras = [
        (etq, cant, ok_, int(calificar.redondear(100 * cant / s["total"], 0)) if s["total"] else 0) for etq, cant, ok_ in p.barras
    ]
    p.es_grafico = p.tipo in ("opcion", "multiple", "desplegable", "vf", "escala")
    p.es_cuadricula = p.tipo in ("cuadricula", "cuadricula_casillas")
    p.tabla = [(fila, [s["grid"].get(fila.pk, {}).get(c.pk, 0) for c in p.columnas]) for fila in p.filas]
    p.textos_mostrados = []
    for quien, texto, rid in s["textos"][:30]:
        if p.tipo == "fecha" and texto:
            try:
                texto = datetime.strptime(texto, "%Y-%m-%d").strftime("%d/%m/%Y")
            except ValueError:
                pass
        p.textos_mostrados.append((quien, texto, rid))
    p.mas_textos = max(0, len(s["textos"]) - 30)


@exigir()
def descargar(request, id):
    """Todas las respuestas en una tabla para Excel (como la hoja de cálculo de Google Forms)."""
    f, _modulo, acceso = _formulario(request, id)
    if acceso == "alumno":
        return prohibido(request)
    preguntas = [p for p in f.preguntas_completas() if not p.es_seccion]
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="respuestas-{slugify(f.titulo) or "formulario"}.csv"'
    respuesta["X-Content-Type-Options"] = "nosniff"
    respuesta.write("﻿")
    w = csv.writer(respuesta, delimiter=";")
    cabecera = ["Fecha", "Apellidos", "Nombres", "Correo / DNI"]
    if not f.es_encuesta:
        cabecera.append("Nota")
    cabecera += [p.enunciado if len(p.enunciado) <= 120 else p.enunciado[:119] + "…" for p in preguntas]
    w.writerow(csv_fila(cabecera))
    intentos = (
        calificar.terminados(f)
        .select_related("alumno")
        .prefetch_related("respuestas")
        .order_by("alumno__apellidos", "alumno__nombres", "id")
    )
    for i in intentos:
        por_pregunta = {r.pregunta_id: r for r in i.respuestas.all()}
        fila = [
            timezone.localtime(i.fin).strftime("%d/%m/%Y %H:%M"),
            i.alumno.apellidos,
            i.alumno.nombres,
            i.alumno.correo or i.alumno.dni,
        ]
        if not f.es_encuesta:
            fila.append(nota_fmt(i.nota).replace(".", ",") if i.nota is not None else "Por revisar")
        fila += [calificar.texto_respuesta(p, por_pregunta.get(p.pk)) for p in preguntas]
        w.writerow(csv_fila(fila))
    return respuesta


@exigir(Rol.DOCENTE, Rol.ADMIN)
def plantilla(request):
    """Plantilla para llenar en Excel con las preguntas."""
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="plantilla-preguntas.csv"'
    respuesta.write("﻿")
    w = csv.writer(respuesta, delimiter=";")
    w.writerows(
        [
            [
                "Tipo",
                "Pregunta",
                "Opción A",
                "Opción B",
                "Opción C",
                "Opción D",
                "Correcta",
                "Puntos",
                "Obligatoria",
                "Explicación",
            ],
            [
                "opciones",
                "¿Qué herramienta se usa para desenredar el cabello?",
                "Navaja",
                "Peine de dientes anchos",
                "Secadora",
                "",
                "B",
                "2",
                "sí",
                "El peine ancho no rompe el cabello.",
            ],
            [
                "casillas",
                "¿Cuáles son elementos de bioseguridad?",
                "Guantes",
                "Mascarilla",
                "Anillos",
                "Capa",
                "A,B,D",
                "3",
                "sí",
                "",
            ],
            ["vf", "Se debe desinfectar la tijera después de cada cliente.", "", "", "", "", "Verdadero", "1", "sí", ""],
            [
                "corta",
                "¿Cómo se llama el corte de corto a largo gradual?",
                "",
                "",
                "",
                "",
                "degrafilado | degradado",
                "2",
                "sí",
                "",
            ],
            ["parrafo", "Explica cómo recibes a un cliente.", "", "", "", "", "", "2", "no", ""],
            ["desplegable", "¿En qué turno estudias?", "Mañana", "Tarde", "Noche", "", "", "0", "sí", ""],
        ]
    )
    return respuesta


editar_o_actualizar = por_metodo(GET=editar, POST=actualizar)
