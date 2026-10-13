"""Módulos y clases: lo que ven y hacen el docente y el alumno (mismas pantallas y direcciones que el sistema anterior)."""

import re
from datetime import date

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.cuentas.models import Rol
from apps.nucleo import ajustes, limites
from apps.nucleo.models import Notificacion, Registro
from apps.nucleo.permisos import Detener, exigir, no_encontrado, prohibido
from apps.nucleo.utils import (
    clave_segura,
    error,
    fecha_larga,
    ip_cliente,
    ok,
    plural,
    por_metodo,
    url_absoluta,
    vista,
    volver_con_error,
)

from . import contenido
from .models import Aviso, Clase, EstadoClase, Modulo, PreguntaClase, Turno, UnidadDidactica
from .views_admin import contexto_unidades

# ---------- Quién puede ver el módulo ----------


def cargar_modulo(request, id):
    """Carga un módulo y verifica que la persona pueda verlo. Devuelve (módulo, acceso) donde acceso es
    «docente» (el dueño), «alumno» o «lectura» (administración y dirección)."""
    u = request.user
    modulo = Modulo.objects.con_alumnos().filter(pk=id).first()
    if modulo is None:
        raise Detener(no_encontrado(request))
    if u.rol == Rol.DOCENTE and modulo.docente_id == u.pk:
        acceso = "docente"
    elif u.rol == Rol.ALUMNO and modulo.es_alumno(u):
        acceso = "alumno"
    elif u.rol in (Rol.ADMIN, Rol.DIRECCION):
        acceso = "lectura"
    else:
        raise Detener(prohibido(request))
    return modulo, acceso


def modulo_del_docente(request, id):
    """Igual que `cargar_modulo`, pero solo deja pasar al docente del módulo (para guardar cambios)."""
    modulo, acceso = cargar_modulo(request, id)
    if acceso != "docente":
        raise Detener(prohibido(request))
    return modulo


def clase_del_docente(request, clase_id):
    clase = Clase.objects.filter(pk=clase_id).select_related("modulo").first()
    if clase is None:
        raise Detener(no_encontrado(request))
    modulo_del_docente(request, clase.modulo_id)
    return clase


def _fecha(texto):
    """Fecha AAAA-MM-DD válida, o None."""
    try:
        return date.fromisoformat(texto) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto or "") else None
    except ValueError:
        return None


def _entrada(request, clave):
    return (request.POST.get(clave) or "").strip()


# ---------- Mis módulos ----------


@exigir()
def modulos(request):
    u = request.user
    if u.rol == Rol.ALUMNO:
        return _mis_modulos_alumno(request)
    if u.rol == Rol.DOCENTE:
        lista = Modulo.objects.con_alumnos().filter(docente=u, activo=True).order_by("nombre")
    else:
        lista = Modulo.objects.con_alumnos().order_by("-activo", "especialidad", "nombre")
    grupos = {}
    for m in lista:
        grupos.setdefault(m.especialidad, []).append(m)
    return vista(
        request,
        "cursos/index.html",
        {"grupos": grupos, "hay": bool(lista), "rol": u.rol},
        titulo="Todos los módulos" if u.rol in (Rol.ADMIN, Rol.DIRECCION) else "Mis módulos",
        sub="Toca un módulo para entrar",
        menu="cursos",
    )


def datos_de_modulo_alumno(modulo, alumno):
    """Avance, asistencia y clase de ahora de un módulo, para las tarjetas del alumno."""
    items = contenido.items_del_modulo(modulo, alumno, "alumno")
    clases = list(modulo.clases.filter(visible=True))
    resumen = contenido.resumen_alumno(modulo, alumno)
    return {
        **contenido.avance_alumno(items),
        "finalizado": Clase.terminadas(clases),
        "actual": Clase.actual(clases),
        "asistencia": resumen["asistencia"],
    }


def _mis_modulos_alumno(request):
    u = request.user
    lista = list(Modulo.objects.con_alumnos().filter(matriculas__alumno=u, activo=True).order_by("nombre"))
    for m in lista:
        m.datos = datos_de_modulo_alumno(m, u)
    pendientes, grupos = contenido.pendientes_agrupados(u)
    return vista(
        request,
        "cursos/alumno.html",
        {"modulos": lista, "bloques_pendientes": contenido.bloques_de_pendientes(grupos), "total": len(pendientes)},
        titulo="Mis módulos",
        sub="Busca un módulo o toca uno para entrar",
        menu="cursos",
    )


# ---------- El docente crea y edita su módulo ----------


def _formulario_docente(request, modulo, didacticas):
    old = request.session.get("_old", {})

    def v(campo, defecto=""):
        return old.get(campo, getattr(modulo, campo, defecto) if modulo else defecto) or defecto

    seleccion = (v("modulo") or "Módulo 1").replace("Módulo II", "Módulo 2").replace("Módulo I", "Módulo 1")
    return {
        "modulo": modulo,
        "es": modulo is not None,
        "especialidades": ajustes.nombres_especialidades(),
        "esp": v("especialidad"),
        "mod_sel": seleccion,
        "v": {
            "nombre": v("nombre"),
            "turno": v("turno", "mañana"),
            "horario": v("horario"),
            "whatsapp_grupo": v("whatsapp_grupo"),
        },
        "turnos": Turno.choices,
        **contexto_unidades(request, didacticas),
        **_contexto_temas(request),
    }


def _contexto_temas(request):
    """Campos para crear varias clases (una fila por clase y, si se quiere, fechas seguidas)."""
    old = request.session.get("_old", {})
    valores = [t for t in (old.get("temas[]") or [])] or ["", "", ""]
    ejemplos = ["Higiene y seguridad en el taller", "Corte básico", "Corte degrafilado", "Tintes y mechas"]
    return {
        "temas_filas": [
            {"n": i + 1, "valor": v, "ejemplo": ejemplos[i] if i < len(ejemplos) else "Tema de la clase"}
            for i, v in enumerate(valores)
        ],
        "con_fechas": old.get("con_fechas", "1") != "",
        "desde": old.get("desde", date.today().isoformat()),
        "dias": old.get("dias", "7"),
    }


@exigir(Rol.DOCENTE)
def nuevo(request):
    return vista(
        request,
        "cursos/form.html",
        {**_formulario_docente(request, None, []), "prefijo": "nuevo"},
        titulo="Crear un módulo",
        sub="Tus alumnos entrarán con un código",
        volver=reverse("academico:modulos"),
        menu="cursos",
    )


def _leer_formulario(request, volver):
    """Lee y revisa el formulario del docente. Devuelve (datos, unidades) o lanza `Detener` con el error."""
    p = request.POST
    esp, turno = _entrada(request, "especialidad"), _entrada(request, "turno")
    datos = {
        "nombre": _entrada(request, "nombre")[:150],
        "especialidad": esp if esp in ajustes.nombres_especialidades() else "",
        "modulo": _entrada(request, "modulo")[:100],
        "turno": turno if turno in Turno.values else "",
        "horario": _entrada(request, "horario")[:120],
    }
    grupo = _entrada(request, "whatsapp_grupo")[:300]
    if grupo and not re.match(r"https://(chat\.whatsapp\.com|wa\.me|api\.whatsapp\.com|whatsapp\.com)/", grupo, re.I):
        raise Detener(
            volver_con_error(request, volver, "El enlace del grupo de WhatsApp debe empezar con https://chat.whatsapp.com/")
        )
    if not (datos["especialidad"] and datos["modulo"] and datos["turno"]):
        raise Detener(volver_con_error(request, volver, "Elige el curso, el módulo y el turno."))
    if not datos["nombre"]:
        datos["nombre"] = f"{datos['especialidad']} – {datos['modulo']}"  # ej. «Peluquería y Barbería – Módulo 1»
    unidades, falla = UnidadDidactica.de_formulario(p)
    if falla is not None:
        raise Detener(volver_con_error(request, volver, falla))
    datos["whatsapp_grupo"] = grupo
    return datos, unidades


def _temas_del_formulario(request):
    """Los temas de las clases: una fila por clase («temas[]»), o un texto con un tema por línea."""
    lista = request.POST.getlist("temas[]") or request.POST.getlist("temas")
    return Clase.temas_de_texto("\n".join(t.strip() for t in lista))


@require_POST
@exigir(Rol.DOCENTE)
def guardar(request):
    u = request.user
    datos, unidades = _leer_formulario(request, reverse("academico:nuevo"))
    modulo = Modulo.crear(periodo=ajustes.ajuste("periodo"), docente=u, **datos)
    UnidadDidactica.guardar_lista(modulo, unidades)
    temas = _temas_del_formulario(request)
    if temas:
        desde = _fecha(_entrada(request, "desde")) if "con_fechas" in request.POST else None
        try:
            dias = max(1, min(int(request.POST.get("dias", 7)), 120))
        except ValueError:
            dias = 7
        Clase.planificar(modulo, temas, desde, dias)
    ok(
        request,
        "Módulo creado"
        + (f" con {plural(len(temas), 'clase', 'clases')}" if temas else "")
        + ". Comparte el código con tus alumnos para que se inscriban.",
    )
    return redirect("academico:modulo", id=modulo.pk)


@exigir(Rol.DOCENTE)
def editar(request, id):
    m = modulo_del_docente(request, id)
    return vista(
        request,
        "cursos/form.html",
        _formulario_docente(request, m, list(m.unidades_didacticas.all())),
        titulo="Editar módulo",
        sub=m.nombre,
        volver=reverse("academico:modulo", args=[id]),
        menu="cursos",
    )


@require_POST
@exigir(Rol.DOCENTE)
def actualizar(request, id):
    m = modulo_del_docente(request, id)
    datos, unidades = _leer_formulario(request, reverse("academico:editar", args=[id]))
    for campo in ("nombre", "especialidad", "modulo", "turno", "horario", "whatsapp_grupo"):
        setattr(m, campo, datos[campo])
    m.save(update_fields=["nombre", "especialidad", "modulo", "turno", "horario", "whatsapp_grupo"])
    UnidadDidactica.guardar_lista(m, unidades)
    ok(request, "Cambios guardados.")
    return redirect("academico:modulo", id=id)


def _motivo_no_eliminar(modulo):
    """Por qué el docente no puede eliminar este módulo (o None si puede). Los trabajos, las notas y la asistencia de
    los alumnos son registros del CETPRO: un módulo que ya los tiene o que está archivado solo lo elimina el administrador."""
    if not modulo.activo:
        return "Este módulo está archivado: pídele al administrador que lo elimine."
    if modulo.tiene_registros_de_alumnos():
        return "Este módulo ya tiene trabajos, tests o asistencia de alumnos. Esos registros son del CETPRO: pídele al administrador que lo elimine."
    return None


@exigir(Rol.DOCENTE)
def confirmar_eliminar(request, id):
    m = modulo_del_docente(request, id)
    motivo = _motivo_no_eliminar(m)
    if motivo:
        error(request, motivo)
        return redirect("academico:modulo", id=id)
    return vista(
        request,
        "cursos/eliminar.html",
        {
            "modulo": m,
            "resumen": m.resumen_al_eliminar(),
            "accion": reverse("academico:eliminar", args=[id]),
            "cancelar": reverse("academico:modulo", args=[id]),
        },
        titulo="Eliminar módulo",
        sub="Revisa antes de borrar",
        volver=reverse("academico:modulo", args=[id]),
        menu="cursos",
    )


@require_POST
@exigir(Rol.DOCENTE)
def eliminar(request, id):
    u = request.user
    m = modulo_del_docente(request, id)
    motivo = _motivo_no_eliminar(m)
    if motivo:
        error(request, motivo)
        return redirect("academico:modulo", id=id)
    resumen = m.resumen_al_eliminar()
    if resumen and "entiendo" not in request.POST:
        return volver_con_error(
            request, reverse("academico:eliminar", args=[id]), "Marca la casilla «Entiendo» para poder eliminar el módulo."
        )
    nombre = m.nombre
    m.eliminar_completo()
    Registro.anotar(
        u,
        "modulo",
        f"{u.nombre_completo} eliminó su módulo «{nombre}»." + (f" Se borró también: {', '.join(resumen)}." if resumen else ""),
        request,
    )
    ok(request, f"Módulo eliminado: «{nombre}».")
    return redirect("academico:modulos")


@require_POST
@exigir(Rol.DOCENTE)
def codigo(request, id):
    """Código de inscripción: nuevo código, abrir o cerrar inscripciones."""
    m = modulo_del_docente(request, id)
    accion = _entrada(request, "accion")
    if accion == "nuevo":
        m.nuevo_codigo()
        mensaje = f"Nuevo código: {m.codigo_fmt}. El anterior ya no sirve."
    else:
        m.inscripcion_abierta = accion != "cerrar"
        m.save(update_fields=["inscripcion_abierta"])
        mensaje = (
            "Inscripciones cerradas: nadie más puede entrar con el código."
            if accion == "cerrar"
            else "Inscripciones abiertas: tus alumnos ya pueden entrar con el código."
        )
    ok(request, mensaje)
    return redirect("academico:alumnos", id=id)


# ---------- Página del módulo ----------


def _frase_de_clase(c, acceso, k):
    """Texto bajo el título de cada clase en la página del módulo."""
    sit = c.situacion
    if sit == "proxima":
        frase = "Se abre " + (f"el {fecha_larga(c.fecha_inicio)}" if c.fecha_inicio else "pronto")
    elif acceso == "alumno":
        p = k["pendientes"]
        if p:
            frase = f"Tienes {plural(p, 'tarea por hacer', 'tareas por hacer')}"
        else:
            frase = "Todo hecho" if (k["tareas"] or k["materiales"]) else "Sin tareas por ahora"
    else:
        partes = []
        if k["materiales"]:
            partes.append(plural(k["materiales"], "material", "materiales"))
        if k["tareas"]:
            partes.append(plural(k["tareas"], "tarea", "tareas"))
        frase = " · ".join(partes) if partes else "Vacía: entra para subir material o crear tareas"
    if sit == "cerrada":
        frase += " · Ya terminó"
    elif sit == "abierta" and c.fecha_fin:
        frase += f" · Hasta el {fecha_larga(c.fecha_fin)}"
    return frase


@exigir()
def ver(request, id):
    """Página principal de un módulo: sus clases y los accesos a notas, asistencia y alumnos."""
    u = request.user
    m, acceso = cargar_modulo(request, id)
    if acceso == "docente" and not m.codigo:
        m.nuevo_codigo()  # módulos creados antes de la versión 2
    es_alumno, es_docente = acceso == "alumno", acceso == "docente"
    clases = list(m.clases.filter(visible=True) if es_alumno else m.clases.all())
    items = contenido.items_del_modulo(m, u, acceso)
    por_clase_, cuenta = contenido.por_clase(items)
    actual = Clase.actual(clases)
    datos = {
        "modulo": m,
        "acceso": acceso,
        "es_docente": es_docente,
        "es_alumno": es_alumno,
        "avisos": list(m.avisos.select_related("autor")[:3]),
        "didacticas": list(m.unidades_didacticas.all()),
        "puede_eliminar": es_docente and _motivo_no_eliminar(m) is None,
        "total_clases": len(clases),
    }
    datos["tot_creditos"], datos["tot_horas"] = UnidadDidactica.totales(datos["didacticas"])
    if es_alumno:
        datos.update(contenido.avance_alumno(items))
        datos["hacer"] = sorted(
            (it for it in items if it.pendiente), key=lambda it: it.limite.timestamp() if it.limite else float("inf")
        )
        datos["resumen"] = contenido.resumen_alumno(m, u)
        datos["asistencia"] = datos["resumen"]["asistencia"]
    else:
        datos["sin_calificar"] = contenido.por_calificar(m)
        datos["asistencia_hoy"] = contenido.asistencia_hoy(m)["tomada_hoy"]
    for n, c in enumerate(clases, start=1):
        c.n = n
        c.cont = por_clase_.get(c.pk, {"materiales": [], "tareas": []})
        c.k = cuenta.get(c.pk, {"materiales": 0, "tareas": 0, "pendientes": 0})
        c.es_actual = bool(actual and actual.pk == c.pk and c.situacion == "abierta")
        c.bloqueada = es_alumno and c.situacion == "proxima"
        c.frase = _frase_de_clase(c, acceso, c.k)
        c.destacar = es_alumno and c.k["pendientes"] and c.situacion == "abierta"
        c.vacia = not c.cont["materiales"] and not c.cont["tareas"]
    datos["clases"] = clases
    if es_docente:
        todos = list(m.alumnos())
        datos["alumnos_modulo"] = todos[:8]
        datos["total_alumnos_modulo"] = len(todos)
        datos["texto_wa"] = (
            f"Inscríbete en mi módulo «{m.nombre}» del {ajustes.ajuste('centro_nombre')}. Entra a "
            f"{url_absoluta(request, reverse('cuentas:registro'))} , escribe tu DNI y este código: {m.codigo_fmt}"
        )
        datos.update(contexto_temas_ver(request, len(clases)))
    return vista(
        request,
        "cursos/ver.html",
        datos,
        titulo=m.nombre,
        sub=f"{m.especialidad} · Prof. {m.docente.nombre_completo}",
        volver=reverse("academico:modulos"),
        menu="cursos",
    )


def contexto_temas_ver(request, cuantas):
    return {**_contexto_temas(request), "prefijo": "plan", "n_siguiente": cuantas + 1}


# ---------- Clases ----------


@exigir()
def clases_redirigir(request, id):
    """Antes había una página aparte con todas las clases: ahora están en la página del módulo."""
    cargar_modulo(request, id)
    clase = request.GET.get("clase") or request.GET.get("semana") or ""
    if clase.isdigit():
        return redirect("academico:clase", id=int(clase))
    return redirect(reverse("academico:modulo", args=[id]) + "#clases")


@exigir()
def clase(request, id):
    """Una clase: sus materiales, tareas y formularios. El docente sube material y crea tareas desde aquí."""
    u = request.user
    c = Clase.objects.filter(pk=id).select_related("modulo").first()
    if c is None:
        return no_encontrado(request)
    m, acceso = cargar_modulo(request, c.modulo_id)
    es_alumno = acceso == "alumno"
    if es_alumno and (c.situacion == "proxima" or not c.visible):
        return vista(
            request,
            "cursos/clase_bloqueada.html",
            {"modulo": m, "clase": c},
            titulo=c.titulo,
            sub=m.nombre,
            volver=reverse("academico:modulo", args=[m.pk]),
            menu="cursos",
        )
    todas = list(m.clases.filter(visible=True) if es_alumno else m.clases.all())
    numero = next((i for i, x in enumerate(todas, start=1) if x.pk == c.pk), 0)
    items = [it for it in contenido.items_del_modulo(m, u, acceso) if it.clase_id == c.pk]
    return vista(
        request,
        "cursos/clase.html",
        {
            "modulo": m,
            "clase": c,
            "numero": numero,
            "acceso": acceso,
            "es_docente": acceso == "docente",
            "es_alumno": es_alumno,
            "materiales": [i for i in items if i.tipo == "material"],
            "tareas": [i for i in items if i.tipo != "material"],
            "preguntas": PreguntaClase.de_clase(c),
            "puede_preguntar": acceso != "lectura" and not (es_alumno and c.situacion == "proxima"),
            "estados": EstadoClase.choices,
            "max_mb": settings.ARCHIVOS_MAX_MB,
        },
        titulo=f"Clase {numero}: {c.titulo}",
        sub=m.nombre,
        volver=reverse("academico:modulo", args=[m.pk]) + "#clases",
        menu="cursos",
    )


@exigir(Rol.DOCENTE)
def nueva_actividad(request, id):
    """«Crear tarea» desde fuera de una clase: lleva a la clase de ahora."""
    m = modulo_del_docente(request, id)
    actual = Clase.actual(list(m.clases.all()))
    if actual is None:
        ok(request, "Primero crea las clases del módulo. Después, dentro de cada clase, creas sus tareas.")
        return redirect(reverse("academico:modulo", args=[id]) + "#agregar-clases")
    return redirect(reverse("academico:clase", args=[actual.pk]) + "#crear")


def _fechas_de_clase(request, volver):
    ini_txt, fin_txt = _entrada(request, "fecha_inicio"), _entrada(request, "fecha_fin")
    ini, fin = _fecha(ini_txt), _fecha(fin_txt)
    if (ini_txt and ini is None) or (fin_txt and fin is None):
        raise Detener(volver_con_error(request, volver, "Revisa las fechas de la clase."))
    if ini and fin and fin < ini:
        raise Detener(volver_con_error(request, volver, "La fecha de cierre debe ser después de la fecha de inicio."))
    return ini, fin


@require_POST
@exigir(Rol.DOCENTE)
def crear_clase(request, id):
    """Agrega una clase (con fechas opcionales)."""
    m = modulo_del_docente(request, id)
    volver = reverse("academico:modulo", args=[id]) + "#agregar-clases"
    tema = _entrada(request, "tema")[:150]
    if not tema:
        return volver_con_error(request, volver, "Escribe el tema de la clase.")
    ini, fin = _fechas_de_clase(request, volver)
    nueva = Clase.crear(m, tema, ini, fin, _entrada(request, "descripcion")[:2000])
    ok(request, "Clase agregada. Ahora sube materiales o crea tareas.")
    return redirect("academico:clase", id=nueva.pk)


@require_POST
@exigir(Rol.DOCENTE)
def planificar(request, id):
    """Crea varias clases: un tema por línea; con fechas seguidas si el docente lo pide."""
    m = modulo_del_docente(request, id)
    volver = reverse("academico:modulo", args=[id]) + "#agregar-clases"
    temas = _temas_del_formulario(request)
    con_fechas = "con_fechas" in request.POST
    try:
        dias = int(request.POST.get("dias", 0))
    except ValueError:
        dias = 0
    desde = _fecha(_entrada(request, "desde")) if con_fechas else None
    if not temas:
        return volver_con_error(request, volver, "Escribe el tema de al menos una clase.")
    if con_fechas and (dias < 1 or dias > 120 or desde is None):
        return volver_con_error(request, volver, "Revisa cuántos días dura cada clase y desde qué fecha empiezan.")
    n = Clase.planificar(m, temas, desde, max(1, dias))
    ok(
        request,
        plural(n, "clase creada", "clases creadas") + (". Se abrirán y cerrarán solas en sus fechas." if con_fechas else "."),
    )
    return redirect(reverse("academico:modulo", args=[id]) + "#clases")


@require_POST
@exigir(Rol.DOCENTE)
def mover_clase(request, id):
    """Cambia el lugar de una clase (antes o después)."""
    c = clase_del_docente(request, id)
    c.mover(_entrada(request, "dir") == "antes")
    ok(request, "Orden de las clases cambiado.")
    return redirect(reverse("academico:modulo", args=[c.modulo_id]) + "#clases")


def actualizar_clase(request, id):
    c = clase_del_docente(request, id)
    tema = _entrada(request, "tema")[:150]
    volver = reverse("academico:clase", args=[id])
    if not tema:
        return volver_con_error(request, volver + "#editar", "Escribe el tema de la clase.")
    ini, fin = _fechas_de_clase(request, volver + "#editar")
    c.titulo, c.descripcion, c.fecha_inicio, c.fecha_fin = tema, _entrada(request, "descripcion")[:2000], ini, fin
    c.save(update_fields=["titulo", "descripcion", "fecha_inicio", "fecha_fin"])
    ok(request, "Clase guardada.")
    return redirect(volver)


@require_POST
@exigir(Rol.DOCENTE)
def estado_clase(request, id):
    """Abrir ya, cerrar ya, o volver a «según las fechas»."""
    c = clase_del_docente(request, id)
    estado = _entrada(request, "estado")
    if estado in EstadoClase.values:
        c.estado = estado
        c.save(update_fields=["estado"])
    mensajes = {
        "abierta": "Clase abierta: tus alumnos ya la ven y pueden entregar.",
        "cerrada": "Clase cerrada: tus alumnos ven los materiales, pero ya no pueden entregar.",
    }
    ok(request, mensajes.get(estado, "La clase se abrirá y cerrará sola según sus fechas."))
    return redirect("academico:clase", id=id)


@require_POST
@exigir(Rol.DOCENTE)
def eliminar_clase(request, id):
    c = clase_del_docente(request, id)
    if not c.esta_vacia():
        error(request, "Primero borra los materiales, tareas y formularios de esta clase.")
        return redirect("academico:clase", id=id)
    modulo_id = c.modulo_id
    c.delete()
    ok(request, "Clase borrada.")
    return redirect(reverse("academico:modulo", args=[modulo_id]) + "#clases")


# ---------- Preguntas de la clase ----------


@require_POST
@exigir()
def preguntar(request, id):
    """Hacer una pregunta en la clase, o responder una (si viene «padre»)."""
    u = request.user
    c = Clase.objects.filter(pk=id).select_related("modulo__docente").first()
    if c is None:
        return no_encontrado(request)
    m, acceso = cargar_modulo(request, c.modulo_id)
    if acceso == "lectura" or (acceso == "alumno" and c.situacion == "proxima"):
        return prohibido(request)
    texto = _entrada(request, "texto")[:2000]
    volver = reverse("academico:clase", args=[id]) + "#preguntas"
    if not texto:
        return volver_con_error(request, volver, "Escribe tu pregunta o tu respuesta.")
    padre = None
    if _entrada(request, "padre"):
        padre = PreguntaClase.objects.filter(pk=_entrada(request, "padre") if _entrada(request, "padre").isdigit() else 0).first()
        if padre is None or padre.clase_id != c.pk or padre.padre_id is not None:
            return no_encontrado(request)
    nueva = PreguntaClase.objects.create(clase=c, autor=u, padre=padre, texto=texto)
    enlace = reverse("academico:clase", args=[id]) + f"#pregunta-{padre.pk if padre else nueva.pk}"
    if padre is None and acceso == "alumno":
        Notificacion.crear(m.docente, f"{u.primer_nombre} preguntó en «{c.titulo}»", enlace)
    elif padre is not None and padre.autor_id != u.pk:
        Notificacion.crear(padre.autor, f"Respondieron tu pregunta en «{c.titulo}»", enlace)
    ok(request, "Respuesta enviada." if padre else "Pregunta enviada. Tu profesor la verá y te responderá aquí.")
    return redirect(enlace)


@require_POST
@exigir()
def borrar_pregunta(request, id):
    """El autor o el docente del módulo borra una pregunta o respuesta."""
    u = request.user
    p = PreguntaClase.objects.filter(pk=id).select_related("clase").first()
    if p is None:
        return no_encontrado(request)
    _m, acceso = cargar_modulo(request, p.clase.modulo_id)
    if acceso != "docente" and p.autor_id != u.pk:
        return prohibido(request)
    clase_id = p.clase_id
    p.delete()
    ok(request, "Borrado.")
    return redirect(reverse("academico:clase", args=[clase_id]) + "#preguntas")


# ---------- Avisos del módulo ----------


@require_POST
@exigir(Rol.DOCENTE)
def publicar_aviso(request, id):
    m = modulo_del_docente(request, id)
    texto = _entrada(request, "contenido")[:2000]
    if not texto:
        return volver_con_error(request, reverse("academico:modulo", args=[id]), "Escribe el aviso antes de publicarlo.")
    Aviso.crear(m, request.user, texto)
    resumen = texto if len(texto) <= 120 else texto[:119] + "…"
    Notificacion.a_alumnos(m, f"Nuevo aviso de tu profesor: {resumen}", reverse("academico:modulo", args=[id]))
    ok(request, "Aviso publicado. Tus alumnos ya lo ven en su Inicio.")
    return redirect("academico:modulo", id=id)


@require_POST
@exigir(Rol.DOCENTE)
def eliminar_aviso(request, id):
    a = Aviso.objects.filter(pk=id).first()
    if a is None:
        return no_encontrado(request)
    modulo_del_docente(request, a.modulo_id)
    modulo_id = a.modulo_id
    a.delete()
    ok(request, "Aviso eliminado.")
    return redirect("academico:modulo", id=modulo_id)


# ---------- Alumnos del módulo ----------


@exigir()
def alumnos(request, id):
    m, acceso = cargar_modulo(request, id)
    if acceso == "alumno":
        return prohibido(request)
    asistencia = contenido.asistencia_por_alumno(m)
    lista = list(m.alumnos())
    for a in lista:
        a.asistencia = asistencia.get(a.pk)
    return vista(
        request,
        "cursos/alumnos.html",
        {
            "modulo": m,
            "acceso": acceso,
            "es_docente": acceso == "docente",
            "alumnos": lista,
            "url_registro": url_absoluta(request, reverse("cuentas:registro")),
        },
        titulo="Alumnos",
        sub=m.nombre,
        volver=reverse("academico:modulo", args=[id]),
        menu="cursos",
    )


@require_POST
@exigir(Rol.DOCENTE)
def clave_alumno(request, id, alumno):
    """El docente le da una contraseña nueva a un alumno de su módulo (si la olvidó)."""
    from apps.cuentas.models import Usuario

    u = request.user
    m = modulo_del_docente(request, id)
    a = Usuario.objects.filter(pk=alumno, rol=Rol.ALUMNO).first()
    if a is None or not m.es_alumno(a):
        return no_encontrado(request)
    clave = clave_segura()
    if a.pendiente:
        a.activar(clave)
    else:
        a.set_password(clave)
    a.debe_cambiar_clave = True
    a.save(update_fields=["password", "debe_cambiar_clave"])
    Registro.anotar(u, "clave", f"El docente {u.nombre_completo} dio contraseña nueva a su alumno {a.nombre_completo}.", request)
    request.session["_clave_otro"] = {
        "nombre": a.nombre_completo,
        "usuario": a.dni or a.correo or "",
        "clave": clave,
        "telefono": a.telefono or "",
        "forzar": True,
    }
    return redirect("academico:alumnos", id=id)


@require_POST
@exigir(Rol.DOCENTE)
def quitar_alumno(request, id, alumno):
    from apps.cuentas.models import Usuario

    m = modulo_del_docente(request, id)
    a = Usuario.objects.filter(pk=alumno).first()
    if a is not None:
        m.quitar_alumno(a)
    ok(request, "Alumno quitado del módulo. Sus entregas se conservan.")
    return redirect("academico:alumnos", id=id)


@require_POST
@exigir(Rol.ALUMNO)
def unirse(request):
    """Alumno con sesión que se une a otro módulo con un código."""
    u = request.user
    ip = ip_cliente(request)
    volver = reverse("academico:modulos")
    if limites.superado("codigo-ip:" + ip, 15, 15):
        return volver_con_error(request, volver, "Hubo muchos códigos equivocados. Espera 15 minutos.")
    m = Modulo.por_codigo(_entrada(request, "codigo"))
    if m is None:
        limites.anotar("codigo-ip:" + ip)
        return volver_con_error(request, volver, "Ese código no es correcto. Pide a tu profesor el código de tu módulo.")
    if m.es_alumno(u):
        ok(request, "Ya estás en este módulo.")
        return redirect("academico:modulo", id=m.pk)
    if ajustes.ajuste("registro_abierto") != "1":
        return volver_con_error(
            request, volver, "Las matrículas del periodo están cerradas. Pide ayuda en la secretaría del CETPRO."
        )
    if not m.inscripcion_abierta:
        return volver_con_error(request, volver, "Ese módulo ya no acepta alumnos nuevos. Habla con tu profesor.")
    m.matricular(u)
    ok(request, f"¡Listo! Ya estás en {m.nombre}.")
    return redirect("academico:modulo", id=m.pk)


# ---------- Direcciones con GET y POST ----------

modulos_o_guardar = por_metodo(GET=modulos, POST=guardar)
editar_o_actualizar = por_metodo(GET=editar, POST=actualizar)
eliminar_o_confirmar = por_metodo(GET=confirmar_eliminar, POST=eliminar)
clase_o_actualizar = por_metodo(GET=clase, POST=exigir(Rol.DOCENTE)(require_POST(actualizar_clase)))
clases_o_crear = por_metodo(GET=clases_redirigir, POST=crear_clase)
