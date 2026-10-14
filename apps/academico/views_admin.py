"""Administración de cursos y módulos (solo el administrador)."""

import re
from math import ceil

from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.cuentas.models import Origen, Rol, Usuario
from apps.nucleo import ajustes
from apps.nucleo.models import Registro
from apps.nucleo.permisos import exigir, no_encontrado
from apps.nucleo.utils import clave_segura, error, ok, plural, por_metodo, vista, volver_con_error

from . import cursos as cursos_
from .models import Matricula, Modulo, Turno, UnidadDidactica


def _consulta_volver(request):
    """Filtros de la lista para volver a ella después de una acción: solo «?campo=valor&…»."""
    v = request.POST.get("volver", "")
    return v if re.fullmatch(r"\?[A-Za-z0-9_=&%.+\-]*", v) else ""


def contexto_unidades(request, didacticas):
    """Datos para las filas de unidades didácticas del formulario (lo escrito si volvió con error; si no, lo guardado)."""
    maximo = UnidadDidactica.MAX
    old = request.session.get("_old", {})
    nombres = old.get("ud_nombre[]") or []
    if nombres:
        creditos, horas = old.get("ud_creditos[]", []), old.get("ud_horas[]", [])
        filas = [(n, creditos[i] if i < len(creditos) else "", horas[i] if i < len(horas) else "") for i, n in enumerate(nombres)]
    else:
        filas = [
            (u.nombre, "" if u.creditos is None else str(u.creditos), "" if u.horas is None else str(u.horas)) for u in didacticas
        ]
    visibles = min(maximo, max(3, len(filas) + 1))  # siempre queda una fila libre
    return {
        "ud_filas": [
            {"i": i, "n": f[0], "c": f[1], "h": f[2], "oculta": i >= visibles}
            for i, f in enumerate(filas + [("", "", "")] * (maximo - len(filas)))
        ][:maximo],
        "ud_hay_mas": visibles < maximo,
    }


# ---------- Cursos (programas) ----------


@exigir("admin")
def cursos(request):
    """Cada curso (programa de estudios) con sus módulos adentro."""
    por_curso = {}
    for m in Modulo.objects.activos().con_alumnos().order_by("especialidad", "nombre"):
        por_curso.setdefault(m.especialidad, []).append(m)
    lista = cursos_.lista()
    # Un módulo cuyo curso ya no está en la lista no debe quedar escondido.
    conocidos = {e["nombre"] for e in lista}
    for otro in por_curso:
        if otro not in conocidos:
            lista.append({"nombre": otro, "color": ajustes.color_curso(otro), "foto": None, "slug": cursos_.slug_de(otro)})
    resumen = Modulo.resumen_por_especialidad()
    for c in lista:
        c["resumen"] = resumen.get(c["nombre"], {"modulos": 0, "docentes": 0, "alumnos": 0})
        c["modulos"] = por_curso.get(c["nombre"], [])
        c["mas"] = max(0, len(c["modulos"]) - 5)
        c["modulos"] = c["modulos"][:5]
    return vista(
        request,
        "admin/cursos/index.html",
        {"cursos": lista},
        titulo="Cursos",
        sub="Cada curso con sus módulos",
        menu="admin-cursos",
    )


# ---------- Catálogo de módulos ----------


@exigir("admin")
def modulos(request):
    estado = request.GET.get("estado", "activos")
    estado = estado if estado in ("activos", "archivados", "todos") else "activos"
    periodo = request.GET.get("periodo", "")[:20]
    esp = request.GET.get("especialidad", "")
    esp = esp if esp in ajustes.nombres_especialidades() else ""
    q = request.GET.get("q", "").strip()[:60]
    try:
        por = int(request.GET.get("por", 12))
    except ValueError:
        por = 12
    por = por if por in (12, 24, 48) else 12

    consulta = Modulo.objects.con_alumnos().annotate(
        docente_completo=Concat("docente__nombres", Value(" "), "docente__apellidos")
    )
    if estado == "activos":
        consulta = consulta.filter(activo=True)
    elif estado == "archivados":
        consulta = consulta.filter(activo=False)
    if periodo:
        consulta = consulta.filter(periodo=periodo)
    if esp:
        consulta = consulta.filter(especialidad=esp)
    if q:
        filtro = Q(nombre__icontains=q) | Q(docente_completo__icontains=q)
        solo_codigo = re.sub(r"[^A-Za-z0-9]", "", q)
        if solo_codigo:
            filtro |= Q(codigo__icontains=solo_codigo)
        consulta = consulta.filter(filtro)
    consulta = consulta.order_by("-activo", "especialidad", "nombre")
    total = consulta.count()
    paginas = max(1, ceil(total / por))
    try:
        num = min(max(1, int(request.GET.get("pagina", 1))), paginas)
    except ValueError:
        num = 1
    lista = consulta[(num - 1) * por : num * por]

    filtros = {"estado": estado, "periodo": periodo, "especialidad": esp, "q": q}
    params = {k: v for k, v in {**filtros, "por": "" if por == 12 else por}.items() if v not in ("", None) and v != "activos"}
    from urllib.parse import urlencode

    volver = "?" + urlencode({**params, **({"pagina": num} if num > 1 else {})}) if params or num > 1 else ""
    conteos = Modulo.conteos_admin()
    return vista(
        request,
        "admin/modulos/index.html",
        {
            "modulos": lista,
            "total": total,
            "num_pagina": num,
            "paginas": paginas,
            "por": por,
            "por_opciones": (12, 24, 48),
            "filtros": filtros,
            "conteos": conteos,
            "periodos": Modulo.periodos(),
            "periodo_actual": ajustes.ajuste("periodo"),
            "especialidades": ajustes.nombres_especialidades(),
            "pestanas": [("activos", "Activos"), ("archivados", "Archivados"), ("todos", "Todos")],
            "params": params,
            "volver": volver,
            "desde": (num - 1) * por + 1 if total else 0,
            "hasta": min(total, num * por),
            "base": reverse("academico:admin_modulos"),
            "colores": {e["nombre"]: e["color"] for e in ajustes.especialidades()},
        },
        titulo="Módulos",
        sub="Todos los módulos del aula",
        volver=reverse("academico:admin_cursos"),
        menu="admin-cursos",
    )


@require_POST
@exigir("admin")
def lote(request):
    """Archivar o reactivar varios módulos (o todos los de un periodo)."""
    yo = request.user
    volver = reverse("academico:admin_modulos") + _consulta_volver(request)
    accion = request.POST.get("accion", "").strip()
    if accion == "archivar_periodo":
        periodo = request.POST.get("periodo", "").strip()[:20]
        if not periodo:
            error(request, "Elige qué periodo quieres archivar.")
            return redirect(volver)
        n = Modulo.objects.filter(activo=True, periodo=periodo).update(activo=False)
        Registro.anotar(
            yo,
            "modulo",
            f"{yo.nombre_completo} archivó los módulos del periodo {periodo} ({plural(n, 'módulo', 'módulos')}).",
            request,
        )
        ok(request, f"{plural(n, 'módulo archivado', 'módulos archivados')} del periodo {periodo}.")
        return redirect(volver)
    ids = {int(i) for i in request.POST.getlist("ids[]") if i.isdigit()}
    if not ids:
        error(request, "Marca primero los módulos que quieres archivar o reactivar.")
        return redirect(volver)
    if accion not in ("archivar", "reactivar"):
        error(request, "Elige qué quieres hacer con los módulos marcados.")
        return redirect(volver)
    activo = accion == "reactivar"
    n = Modulo.objects.filter(pk__in=ids).exclude(activo=activo).update(activo=activo)
    Registro.anotar(
        yo, "modulo", f"{yo.nombre_completo} {'reactivó' if activo else 'archivó'} {plural(n, 'módulo', 'módulos')}.", request
    )
    ok(
        request,
        plural(
            n, "módulo reactivado" if activo else "módulo archivado", "módulos reactivados" if activo else "módulos archivados"
        )
        + ".",
    )
    return redirect(volver)


@require_POST
@exigir("admin")
def estado(request, id):
    """Archiva o reactiva un solo módulo."""
    yo = request.user
    m = Modulo.objects.filter(pk=id).first()
    if m is None:
        return no_encontrado(request)
    estaba_activo = m.activo
    m.activo = not estaba_activo
    m.save(update_fields=["activo"])
    Registro.anotar(
        yo, "modulo", f"{yo.nombre_completo} {'archivó' if estaba_activo else 'reactivó'} el módulo «{m.nombre}».", request
    )
    ok(request, "Módulo archivado: ya no lo ven alumnos ni docente." if estaba_activo else "Módulo reactivado.")
    return redirect(reverse("academico:admin_modulos") + _consulta_volver(request))


# ---------- Eliminar (de verdad) ----------


@exigir("admin")
def confirmar_eliminar(request, id):
    """Pantalla de confirmación: muestra todo lo que se pierde al eliminar el módulo."""
    m = Modulo.objects.filter(pk=id).first()
    if m is None:
        return no_encontrado(request)
    return vista(
        request,
        "cursos/eliminar.html",
        {
            "modulo": m,
            "resumen": m.resumen_al_eliminar(),
            "accion": reverse("academico:admin_eliminar", args=[id]),
            "cancelar": reverse("academico:admin_modulos"),
        },
        titulo="Eliminar módulo",
        sub="Revisa antes de borrar",
        volver=reverse("academico:admin_modulos"),
        menu="admin-cursos",
    )


@require_POST
@exigir("admin")
def eliminar(request, id):
    """Elimina el módulo de verdad (con todo lo que tiene). Si tiene datos, hay que marcar «Entiendo»."""
    yo = request.user
    m = Modulo.objects.filter(pk=id).first()
    if m is None:
        return no_encontrado(request)
    resumen = m.resumen_al_eliminar()
    if resumen and "entiendo" not in request.POST:
        return volver_con_error(
            request, reverse("academico:admin_eliminar", args=[id]), "Marca la casilla «Entiendo» para poder eliminar el módulo."
        )
    nombre = m.nombre
    m.eliminar_completo()
    detalle = f"{yo.nombre_completo} eliminó el módulo «{nombre}»." + (
        f" Se borró también: {', '.join(resumen)}." if resumen else ""
    )
    Registro.anotar(yo, "modulo", detalle, request)
    ok(request, f"Módulo eliminado: «{nombre}».")
    return redirect("academico:admin_modulos")


# ---------- Crear y editar ----------


def _modulos_opciones(valor_actual):
    """«Módulo 1» y «Módulo 2»; un módulo antiguo con otro nombre no se pierde al editarlo."""
    seleccion = (valor_actual or "Módulo 1").replace("Módulo II", "Módulo 2").replace("Módulo I", "Módulo 1")
    opciones = ["Módulo 1", "Módulo 2"]
    if seleccion not in opciones:
        opciones.append(seleccion)
    return seleccion, opciones


def formulario_modulo(request, modulo, esp_inicial, didacticas, modulo_inicial=""):
    """Contexto del formulario de módulo (nuevo o editar) del administrador. `modulo_inicial` es «Módulo 1» o «Módulo 2»
    cuando se llega desde un curso con el botón de uno de ellos."""
    old = request.session.get("_old", {})

    def v(campo, defecto=""):
        return old.get(campo, str(getattr(modulo, campo, defecto) or defecto) if modulo else defecto)

    seleccion, opciones = _modulos_opciones(v("modulo") or modulo_inicial)
    return {
        "modulo": modulo,
        "nuevo": modulo is None,
        "docentes": Usuario.objects.docentes(),
        "esp": old.get("especialidad", modulo.especialidad if modulo else esp_inicial),
        "mod_sel": seleccion,
        "mod_opciones": list(enumerate(opciones)),
        "v": {
            "nombre": v("nombre"),
            "periodo": old.get("periodo", modulo.periodo if modulo else ajustes.ajuste("periodo")),
            "turno": old.get("turno", modulo.turno if modulo else "mañana"),
            "horario": v("horario"),
            "docente_id": str(old.get("docente_id", modulo.docente_id if modulo else "")),
        },
        "turnos": Turno.choices,
        "especialidades": ajustes.nombres_especialidades(),
        **contexto_unidades(request, didacticas),
    }


@exigir("admin")
def nuevo(request):
    esp = request.GET.get("especialidad", "")
    esp = esp if esp in ajustes.nombres_especialidades() else ""
    modulo_inicial = request.GET.get("modulo", "")
    modulo_inicial = modulo_inicial if modulo_inicial in ("Módulo 1", "Módulo 2") else ""
    # Si se llegó desde un curso, «Volver» regresa a ese curso
    volver = reverse("academico:admin_curso", args=[cursos_.slug_de(esp)]) if esp else reverse("academico:admin_cursos")
    return vista(
        request,
        "admin/modulos/form.html",
        formulario_modulo(request, None, esp, [], modulo_inicial),
        titulo="Nuevo módulo",
        sub=esp or "Elige el curso al que pertenece",
        volver=volver,
        menu="admin-cursos",
    )


def _leer_formulario(request, volver):
    """Lee y revisa el formulario de módulo. Devuelve (datos, None) o (None, redirección con el error)."""
    p = request.POST
    esp, turno = p.get("especialidad", "").strip(), p.get("turno", "").strip()
    datos = {
        "nombre": p.get("nombre", "").strip()[:150],
        "especialidad": esp if esp in ajustes.nombres_especialidades() else "",
        "modulo": p.get("modulo", "").strip()[:100],
        "periodo": p.get("periodo", "").strip()[:20],
        "turno": turno if turno in Turno.values else "",
        "horario": p.get("horario", "").strip()[:120],
    }
    docente_id = p.get("docente_id", "")
    docente = Usuario.objects.filter(pk=docente_id, rol=Rol.DOCENTE).first() if docente_id.isdigit() else None
    if not (datos["especialidad"] and datos["modulo"] and datos["periodo"] and datos["turno"]):
        return None, volver_con_error(request, volver, "Elige el curso, el módulo, el periodo y el turno.")
    if not datos["nombre"]:
        datos["nombre"] = f"{datos['especialidad']} – {datos['modulo']}"  # ej. «Soporte Técnico… – Módulo 1»
    if docente is None:
        return None, volver_con_error(request, volver, "Elige el docente del módulo.")
    datos["docente"] = docente
    unidades, falla = UnidadDidactica.de_formulario(p)
    if falla is not None:
        return None, volver_con_error(request, volver, falla)
    return (datos, unidades), None


@require_POST
@exigir("admin")
def guardar(request):
    leido, redireccion = _leer_formulario(request, reverse("academico:admin_nuevo"))
    if redireccion:
        return redireccion
    datos, unidades = leido
    m = Modulo.crear(**datos)
    UnidadDidactica.guardar_lista(m, unidades)
    ok(request, "Módulo creado. Ahora agrega a los alumnos o comparte su código.")
    return redirect("academico:admin_alumnos", id=m.pk)


@exigir("admin")
def editar(request, id):
    m = Modulo.objects.filter(pk=id).select_related("docente").first()
    if m is None:
        return no_encontrado(request)
    return vista(
        request,
        "admin/modulos/form.html",
        formulario_modulo(request, m, "", list(m.unidades_didacticas.all())),
        titulo="Editar módulo",
        sub=m.nombre,
        volver=reverse("academico:admin_modulos"),
        menu="admin-cursos",
    )


@require_POST
@exigir("admin")
def actualizar(request, id):
    m = Modulo.objects.filter(pk=id).first()
    if m is None:
        return no_encontrado(request)
    leido, redireccion = _leer_formulario(request, reverse("academico:admin_editar", args=[id]))
    if redireccion:
        return redireccion
    datos, unidades = leido
    for campo, valor in datos.items():
        setattr(m, campo, valor)
    m.activo = "activo" in request.POST
    m.save()
    UnidadDidactica.guardar_lista(m, unidades)
    ok(request, "Cambios guardados.")
    return redirect("academico:admin_modulos")


# ---------- Alumnos del módulo ----------


@exigir("admin")
def alumnos(request, id):
    m = Modulo.objects.filter(pk=id).select_related("docente").first()
    if m is None:
        return no_encontrado(request)
    return vista(
        request,
        "admin/modulos/alumnos.html",
        {"modulo": m, "alumnos": m.alumnos()},
        titulo="Alumnos del módulo",
        sub=m.nombre,
        volver=reverse("academico:admin_modulos"),
        menu="admin-cursos",
    )


@require_POST
@exigir("admin")
def matricular(request, id):
    """Inscribe alumnos pegando una lista, una persona por línea:
    DNI                       (si ya tiene cuenta)
    DNI, Nombres, Apellidos   (si es nuevo: queda pendiente hasta que cree su contraseña con su DNI)
    """
    m = Modulo.objects.filter(pk=id).first()
    if m is None:
        return no_encontrado(request)
    lineas = request.POST.get("lista", "").splitlines()
    agregados = nuevos = 0
    errores = []
    for n, linea in enumerate(lineas):
        linea = linea.strip()
        if not linea:
            continue
        partes = [p.strip() for p in re.split(r"[,;\t]", linea)]
        dni = re.sub(r"\D", "", partes[0] if partes else "")
        if len(dni) != 8:
            errores.append(f"Línea {n + 1}: escribe un DNI de 8 números.")
            continue
        u = Usuario.objects.filter(dni=dni).first()
        if u is None:
            if len(partes) < 3 or not partes[1] or not partes[2]:
                errores.append(f"Línea {n + 1}: el DNI {dni} no tiene cuenta; escribe también nombres y apellidos.")
                continue
            u = Usuario.objects.crear_alumno(dni, partes[1][:100], partes[2][:100], origen=Origen.LISTA)
            nuevos += 1
        elif u.rol != Rol.ALUMNO:
            errores.append(f"Línea {n + 1}: el DNI {dni} no es de un alumno.")
            continue
        agregados += 1 if m.matricular(u) else 0
    msg = plural(agregados, "alumno agregado", "alumnos agregados") + (
        f" ({plural(nuevos, 'nuevo: creará', 'nuevos: crearán')} su contraseña con su DNI en «Crear mi cuenta»)."
        if nuevos
        else "."
    )
    destino = reverse("academico:admin_alumnos", args=[id])
    if errores:
        request.session["_old"] = {"lista": "\n".join(x for x in lineas if x.strip())}
        error(request, f"{msg} Revisa: {' '.join(errores)}")
        return redirect(destino)
    ok(request, msg)
    return redirect(destino)


@require_POST
@exigir("admin")
def accesos(request, id):
    """Da una contraseña temporal a los alumnos del módulo que todavía no eligieron la suya y abre la pantalla
    para enviársela por WhatsApp (se muestra una sola vez). A quien ya eligió la suya no se le toca."""
    yo = request.user
    m = Modulo.objects.filter(pk=id).first()
    if m is None:
        return no_encontrado(request)
    claves = []
    for a in m.alumnos():
        if not a.pendiente and not a.debe_cambiar_clave:
            continue  # ya eligió su contraseña
        clave = clave_segura()
        if a.pendiente:
            a.activar(clave)
        else:
            a.set_password(clave)
            a.save(update_fields=["password"])
        a.debe_cambiar_clave = True
        a.save(update_fields=["debe_cambiar_clave"])
        claves.append(
            {"nombre": a.nombre_completo, "usuario": a.dni or a.correo or "", "clave": clave, "telefono": a.telefono or ""}
        )
    if not claves:
        ok(request, "Todos los alumnos de este módulo ya eligieron su contraseña.")
        return redirect("academico:admin_alumnos", id=id)
    request.session["_claves_lote"] = claves
    Registro.anotar(
        yo,
        "clave",
        f"{yo.nombre_completo} preparó los accesos de {plural(len(claves), 'alumno', 'alumnos')} del módulo «{m.nombre}».",
        request,
    )
    return redirect("cuentas:admin_claves")


@require_POST
@exigir("admin")
def quitar(request, id, alumno):
    Matricula.objects.filter(modulo_id=id, alumno_id=alumno).delete()
    ok(request, "Alumno quitado del módulo. Sus entregas se conservan.")
    return redirect("academico:admin_alumnos", id=id)


modulos_admin = por_metodo(GET=modulos, POST=guardar)
editar_o_actualizar = por_metodo(GET=editar, POST=actualizar)
confirmar_o_eliminar = por_metodo(GET=confirmar_eliminar, POST=eliminar)
alumnos_o_matricular = por_metodo(GET=alumnos, POST=matricular)
