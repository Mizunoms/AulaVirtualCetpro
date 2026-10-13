"""Mensajes privados entre alumno y docente de un mismo módulo, en tres pasos: tus módulos → los mensajes de un módulo →
escribir uno nuevo (mismas pantallas y direcciones que el sistema anterior)."""

from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from apps.academico.models import Matricula, Modulo
from apps.academico.views import cargar_modulo, modulo_del_docente
from apps.cuentas.models import Rol, Usuario
from apps.nucleo import archivos
from apps.nucleo.permisos import Detener, exigir, no_encontrado, prohibido
from apps.nucleo.utils import es_hoy, fecha_larga, ok, plural, por_metodo, vista, volver_con_error

from .models import Conversacion, Mensaje

MAX_TEXTO = 3000
SIN_TEXTO = "Escribe tu mensaje (o adjunta una foto) antes de enviarlo."


# ---------- Ayudas ----------


def _entero(valor):
    """Un número de la dirección o del formulario; 0 si no es un número razonable."""
    valor = (valor or "").strip()
    return int(valor) if valor.isdigit() and len(valor) <= 9 else 0


def _texto(request):
    return (request.POST.get("texto") or "").strip()[:MAX_TEXTO]


def _hay_archivo(request):
    f = request.FILES.get("archivo")
    return f is not None and f.size > 0


def _guardar_adjunto(request, volver):
    """Foto o archivo adjunto al mensaje (opcional): (ruta, nombre), o None si no mandó nada."""
    if not _hay_archivo(request):
        return None
    try:
        return archivos.guardar(request.FILES["archivo"])
    except archivos.ArchivoError as ex:
        raise Detener(volver_con_error(request, volver, str(ex))) from ex


def _modulos_de(u):
    """Los módulos desde los que la persona puede escribir."""
    consulta = Modulo.objects.con_alumnos()
    consulta = consulta.de_alumno(u) if u.rol == Rol.ALUMNO else consulta.de_docente(u)
    return consulta.order_by("nombre")


def _modulo_de_mensajes(request, id):
    """(módulo, acceso), solo si la persona es del módulo (su alumno o su docente)."""
    return cargar_modulo(request, id)


def _participantes(request, curso_id, persona_id):
    """Verifica que la persona y la otra compartan el módulo (alumno ↔ su docente).
    Devuelve (módulo, docente_id, alumno_id, la otra persona)."""
    u = request.user
    modulo = Modulo.objects.select_related("docente").filter(pk=curso_id).first()
    otro = Usuario.objects.filter(pk=persona_id).first()
    if modulo is None or otro is None:
        raise Detener(no_encontrado(request))
    if u.rol == Rol.ALUMNO:
        ok_ = Matricula.objects.filter(modulo=modulo, alumno=u).exists() and modulo.docente_id == persona_id
        docente_id, alumno_id = persona_id, u.pk
    else:
        ok_ = modulo.docente_id == u.pk and Matricula.objects.filter(modulo=modulo, alumno_id=persona_id).exists()
        docente_id, alumno_id = u.pk, persona_id
    if not ok_:
        raise Detener(prohibido(request))
    return modulo, docente_id, alumno_id, otro


def _conversacion_de(request, id):
    """La conversación, solo para sus dos participantes."""
    cv = Conversacion.objects.select_related("modulo", "docente", "alumno").filter(pk=id).first()
    if cv is None:
        raise Detener(no_encontrado(request))
    if request.user.pk not in (cv.docente_id, cv.alumno_id):
        raise Detener(prohibido(request))
    return cv


def _en_mayuscula(texto):
    return texto[:1].upper() + texto[1:]


def _preparar_mensajes(mensajes, u):
    """Agrega a cada mensaje lo que la pantalla necesita: si es mío, el día, si es el último, si es foto."""
    lista = list(mensajes)
    dia_anterior = None
    for i, m in enumerate(lista):
        m.mio = m.autor_id == u.pk
        dia = timezone.localtime(m.creado).date()
        m.dia_nuevo = dia != dia_anterior
        dia_anterior = dia
        m.dia_texto = "Hoy" if es_hoy(m.creado) else _en_mayuscula(fecha_larga(m.creado))
        m.es_ultimo = i == len(lista) - 1
        m.es_foto = archivos.es_imagen(m.archivo_ruta)
    return lista


def _panel(request, modulo, acceso):
    return {
        "modulo": modulo,
        "acceso": acceso,
        "es_alumno": acceso == "alumno",
        "url_nuevo": reverse("mensajes:nuevo") + f"?curso={modulo.pk}",
        "conversaciones": Conversacion.de_usuario(request.user, modulo),
    }


# ---------- Nivel 1: tus módulos ----------


@exigir(Rol.ALUMNO, Rol.DOCENTE)
def index(request):
    u = request.user
    resumen = {}
    for cv in Conversacion.de_usuario(u):
        r = resumen.setdefault(cv.modulo_id, {"sin_leer": 0, "hilos": 0, "ultimo": None})
        r["sin_leer"] += cv.sin_leer
        r["hilos"] += 1
        if cv.ultimo_fecha and (r["ultimo"] is None or cv.ultimo_fecha > r["ultimo"]):
            r["ultimo"] = cv.ultimo_fecha
    modulos = list(_modulos_de(u))
    for m in modulos:
        m.resumen = resumen.get(m.pk, {"sin_leer": 0, "hilos": 0, "ultimo": None})
    return vista(
        request,
        "mensajes/cursos.html",
        {"modulos": modulos, "es_alumno": u.rol == Rol.ALUMNO},
        titulo="Mensajes",
        sub="Escribe a tus profesores" if u.rol == Rol.ALUMNO else "Conversa con tus alumnos",
        menu="mensajes",
    )


# ---------- Nivel 2: los mensajes de un módulo ----------


@exigir(Rol.ALUMNO, Rol.DOCENTE)
def modulo(request, id):
    modulo_, acceso = _modulo_de_mensajes(request, id)
    return vista(
        request,
        "mensajes/index.html",
        {**_panel(request, modulo_, acceso), "activa": None, "mensajes": [], "otro": None, "accion": None},
        titulo="Mensajes",
        sub=modulo_.nombre,
        volver=reverse("mensajes:index"),
        menu="mensajes",
    )


@exigir(Rol.ALUMNO, Rol.DOCENTE)
def ver(request, id):
    cv = _conversacion_de(request, id)
    u = request.user
    cv.marcar_leidos(u)
    modulo_, acceso = _modulo_de_mensajes(request, cv.modulo_id)
    otro = cv.otro(u)
    return vista(
        request,
        "mensajes/index.html",
        {
            **_panel(request, modulo_, acceso),
            "activa": cv.pk,
            "mensajes": _preparar_mensajes(cv.mensajes.all(), u),
            "otro": otro,
            "accion": reverse("mensajes:ver", args=[cv.pk]),
        },
        titulo=otro.nombre_completo,
        sub=modulo_.nombre,
        volver=reverse("mensajes:modulo", args=[cv.modulo_id]),
        menu="mensajes",
    )


@exigir(Rol.ALUMNO, Rol.DOCENTE)
def responder(request, id):
    cv = _conversacion_de(request, id)
    u = request.user
    volver = reverse("mensajes:ver", args=[cv.pk])
    texto = _texto(request)
    if texto == "" and not _hay_archivo(request):
        return volver_con_error(request, volver, SIN_TEXTO)
    adjunto = _guardar_adjunto(request, volver)
    cv.enviar(u, texto, adjunto)
    return redirect(volver + "#ultimo")


# ---------- Nivel 3: escribir un mensaje nuevo ----------


def _miembros(modulo_, acceso):
    """Las personas a las que se puede escribir: el alumno, a su docente; el docente, a sus alumnos."""
    if acceso == "alumno":
        d = modulo_.docente
        return [{"id": d.pk, "nombre": f"Prof. {d.nombre_completo}", "rol": "Docente"}]
    return [{"id": a.pk, "nombre": f"{a.apellidos}, {a.nombres}", "rol": "Alumno"} for a in modulo_.alumnos()]


@exigir(Rol.ALUMNO, Rol.DOCENTE)
def nuevo(request):
    u = request.user
    curso_id = _entero(request.GET.get("curso"))
    if not curso_id:
        modulos = list(_modulos_de(u))
        if len(modulos) != 1:
            return redirect("mensajes:index")
        curso_id = modulos[0].pk
    modulo_, acceso = _modulo_de_mensajes(request, curso_id)
    return vista(
        request,
        "mensajes/nuevo.html",
        {
            "modulo": modulo_,
            "es_docente": acceso == "docente",
            "miembros": _miembros(modulo_, acceso),
            "para_id": (request.GET.get("para") or "")[:12],
        },
        titulo="Nuevo mensaje",
        sub=modulo_.nombre,
        volver=reverse("mensajes:modulo", args=[curso_id]),
        menu="mensajes",
    )


@exigir(Rol.ALUMNO, Rol.DOCENTE)
def enviar_nuevo(request):
    u = request.user
    curso_id = _entero(request.POST.get("curso"))
    modulo_, acceso = _modulo_de_mensajes(request, curso_id)
    volver = reverse("mensajes:nuevo") + f"?curso={curso_id}"
    para = (request.POST.get("para") or "").strip()
    texto = _texto(request)
    if para == "":
        return volver_con_error(request, volver, "Elige a quién le escribes.")
    if texto == "" and not _hay_archivo(request):
        return volver_con_error(request, volver, SIN_TEXTO)

    if para == "todos":
        if acceso != "docente":
            return prohibido(request)
        alumnos = list(modulo_.alumnos())
        if not alumnos:
            return volver_con_error(request, volver, "Este módulo todavía no tiene alumnos.")
        adjunto = _guardar_adjunto(request, volver)
        _enviar_a_todos(modulo_, u, alumnos, texto, adjunto)
        ok(request, f"Mensaje enviado a {plural(len(alumnos), 'alumno', 'alumnos')} de {modulo_.nombre}.")
        return redirect("mensajes:modulo", id=curso_id)

    if not para.isdigit():
        return no_encontrado(request)
    _, docente_id, alumno_id, _otro = _participantes(request, curso_id, _entero(para))
    adjunto = _guardar_adjunto(request, volver)
    cv = Conversacion.obtener_o_crear(modulo_, docente_id, alumno_id)
    cv.enviar(u, texto, adjunto)
    ok(request, "Mensaje enviado.")
    return redirect(reverse("mensajes:ver", args=[cv.pk]) + "#ultimo")


@transaction.atomic
def _enviar_a_todos(modulo_, docente, alumnos, texto, adjunto=None):
    """El mismo mensaje a cada alumno, en privado (cada uno lo recibe en su propia conversación)."""
    for a in alumnos:
        Conversacion.obtener_o_crear(modulo_, docente, a).enviar(docente, texto, adjunto)


# ---------- Abrir la conversación con una persona ----------


@exigir(Rol.ALUMNO, Rol.DOCENTE)
def con(request, curso, persona):
    """Abre la conversación con una persona del módulo; si todavía no hay, el formulario de mensaje nuevo."""
    modulo_, docente_id, alumno_id, _otro = _participantes(request, curso, persona)
    cv = Conversacion.objects.filter(modulo=modulo_, docente_id=docente_id, alumno_id=alumno_id).first()
    if cv:
        return redirect(reverse("mensajes:ver", args=[cv.pk]) + "#ultimo")
    return redirect(reverse("mensajes:nuevo") + f"?curso={curso}&para={persona}")


@exigir(Rol.ALUMNO, Rol.DOCENTE)
def empezar(request, curso, persona):
    modulo_, docente_id, alumno_id, _otro = _participantes(request, curso, persona)
    volver = reverse("mensajes:nuevo") + f"?curso={curso}&para={persona}"
    texto = _texto(request)
    if texto == "" and not _hay_archivo(request):
        return volver_con_error(request, volver, SIN_TEXTO)
    adjunto = _guardar_adjunto(request, volver)
    cv = Conversacion.obtener_o_crear(modulo_, docente_id, alumno_id)
    cv.enviar(request.user, texto, adjunto)
    return redirect(reverse("mensajes:ver", args=[cv.pk]) + "#ultimo")


# ---------- Docente: un mismo mensaje a todo el módulo ----------


@exigir(Rol.DOCENTE)
def todos(request, id):
    modulo_ = modulo_del_docente(request, id)
    return vista(
        request,
        "mensajes/todos.html",
        {"modulo": modulo_, "alumnos": list(modulo_.alumnos())},
        titulo="Mensaje a todos",
        sub=modulo_.nombre,
        volver=reverse("mensajes:modulo", args=[id]),
        menu="mensajes",
    )


@exigir(Rol.DOCENTE)
def enviar_todos(request, id):
    modulo_ = modulo_del_docente(request, id)
    volver = reverse("mensajes:todos", args=[id])
    texto = _texto(request)
    if texto == "":
        return volver_con_error(request, volver, SIN_TEXTO)
    alumnos = list(modulo_.alumnos())
    if not alumnos:
        return volver_con_error(request, volver, "Este módulo todavía no tiene alumnos.")
    _enviar_a_todos(modulo_, request.user, alumnos, texto)
    ok(request, f"Mensaje enviado a {plural(len(alumnos), 'alumno', 'alumnos')} de {modulo_.nombre}.")
    return redirect("mensajes:modulo", id=id)


# ---------- El archivo de un mensaje ----------


@exigir(Rol.ALUMNO, Rol.DOCENTE)
def adjunto(request, id):
    """Abre el archivo de un mensaje: solo los dos participantes."""
    m = Mensaje.objects.select_related("conversacion").filter(pk=id).first()
    if m is None or not m.archivo_ruta:
        return no_encontrado(request)
    if request.user.pk not in (m.conversacion.docente_id, m.conversacion.alumno_id):
        return prohibido(request)
    en_linea = archivos.es_imagen(m.archivo_ruta) or m.archivo_nombre.lower().endswith(".pdf")
    return archivos.enviar(m.archivo_ruta, m.archivo_nombre, en_linea=en_linea)


nuevo_o_enviar = por_metodo(GET=nuevo, POST=enviar_nuevo)
con_o_empezar = por_metodo(GET=con, POST=empezar)
ver_o_responder = por_metodo(GET=ver, POST=responder)
todos_o_enviar = por_metodo(GET=todos, POST=enviar_todos)
