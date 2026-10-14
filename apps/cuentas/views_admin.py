"""Administración de personas (solo el administrador): lista con filtros, crear y editar, contraseñas, activar o desactivar
y eliminar de verdad. Mismas pantallas y direcciones que el sistema anterior (/admin/usuarios/…)."""

import re
from datetime import date
from math import ceil
from urllib.parse import quote, urlencode

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q, Value
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Concat
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.academico.models import Matricula, Modulo
from apps.nucleo import ajustes
from apps.nucleo.menu import url_o_numeral
from apps.nucleo.models import Registro
from apps.nucleo.permisos import exigir, no_encontrado
from apps.nucleo.utils import clave_segura, error, ok, plural, por_metodo, url_absoluta, vista, volver_con_error, whatsapp_url

from . import resumen
from .models import Origen, Rol, Usuario

# Pestañas de la lista de personas
GRUPOS = {
    "": "Todos",
    "docente": "Docentes",
    "alumno": "Alumnos",
    "personal": "Dirección y admin",
    "pendientes": "Sin contraseña",
    "inactivos": "Inactivos",
}
POR_PAGINA = (10, 25, 50)
MAX_ELIMINAR = 300  # cuentas que se revisan de una vez al eliminar


def _consulta_volver(request):
    """Filtros de la lista para volver a ella después de una acción: solo «?campo=valor&…»."""
    v = request.POST.get("volver", "")
    return v if re.fullmatch(r"\?[A-Za-z0-9_=&%.+\-]*", v) else ""


def _ids(request):
    """Los números de las personas marcadas (sin repetir, sin ceros)."""
    return list(
        dict.fromkeys(int(x) for x in request.POST.getlist("ids[]") + request.POST.getlist("ids") if x.isdigit() and int(x))
    )


def _filtrar(filtros):
    consulta = Usuario.objects.all()
    rol = filtros["rol"]
    if rol == "pendientes":
        consulta = consulta.filter(rol=Rol.ALUMNO, password__startswith="!", is_active=True)
    elif rol == "inactivos":
        consulta = consulta.filter(is_active=False)
    elif rol == "personal":
        consulta = consulta.filter(rol__in=[Rol.DIRECCION, Rol.ADMIN])
    elif rol in Rol.values:
        consulta = consulta.filter(rol=rol)
    q = filtros["q"]
    if q:
        consulta = consulta.annotate(
            nombre_a=Concat("nombres", Value(" "), "apellidos"), nombre_b=Concat("apellidos", Value(" "), "nombres")
        ).filter(Q(dni__startswith=q) | Q(correo__icontains=q) | Q(nombre_a__icontains=q) | Q(nombre_b__icontains=q))
    esp, turno = filtros["especialidad"], filtros["turno"]
    if esp or turno:
        cursa = Matricula.objects.filter(alumno=OuterRef("pk"), modulo__activo=True)
        dicta = Modulo.objects.filter(docente=OuterRef("pk"), activo=True)
        if esp:
            cursa, dicta = cursa.filter(modulo__especialidad=esp), dicta.filter(especialidad=esp)
        if turno:
            cursa, dicta = cursa.filter(modulo__turno=turno), dicta.filter(turno=turno)
        consulta = consulta.filter(Exists(cursa) | Exists(dicta))
    return consulta.order_by("apellidos", "nombres")


def _conteos():
    """Cuántas personas hay en cada pestaña de la lista."""
    pendientes = Q(rol=Rol.ALUMNO, password__startswith="!", is_active=True)
    return Usuario.objects.aggregate(
        todos=Count("id"),
        docente=Count("id", filter=Q(rol=Rol.DOCENTE)),
        alumno=Count("id", filter=Q(rol=Rol.ALUMNO)),
        personal=Count("id", filter=Q(rol__in=[Rol.DIRECCION, Rol.ADMIN])),
        pendientes=Count("id", filter=pendientes),
        inactivos=Count("id", filter=Q(is_active=False)),
    )


def _modulos_de(ids):
    """Módulos activos de varias personas (los que cursan o dictan): {id de persona: [módulos]}"""
    r = {}
    for m in Matricula.objects.filter(alumno__in=ids, modulo__activo=True).select_related("modulo").order_by("modulo__nombre"):
        r.setdefault(m.alumno_id, []).append(m.modulo)
    for m in Modulo.objects.filter(docente__in=ids, activo=True).order_by("nombre"):
        r.setdefault(m.docente_id, []).append(m)
    return r


# ===================================================================== La lista


@exigir(Rol.ADMIN)
def personas(request):
    rol = request.GET.get("rol", "")
    rol = rol if rol in GRUPOS or rol in Rol.values else ""
    q = request.GET.get("q", "").strip()[:60]
    esp = request.GET.get("especialidad", "")
    esp = esp if esp in ajustes.nombres_especialidades() else ""
    turno = request.GET.get("turno", "")
    turno = turno if turno in ("mañana", "tarde", "noche") else ""
    try:
        por = int(request.GET.get("por", 25))
    except ValueError:
        por = 25
    por = por if por in POR_PAGINA else 25
    filtros = {"rol": rol, "q": q, "especialidad": esp, "turno": turno}
    consulta = _filtrar(filtros)
    total = consulta.count()
    paginas = max(1, ceil(total / por))
    try:
        num = min(max(1, int(request.GET.get("pagina", 1))), paginas)
    except ValueError:
        num = 1
    usuarios = list(consulta[(num - 1) * por : num * por])
    modulos = _modulos_de([u.pk for u in usuarios])
    for u in usuarios:
        u.modulos_activos = modulos.get(u.pk, [])
        u.modulos_primeros = u.modulos_activos[:2]
        u.modulos_mas = max(0, len(u.modulos_activos) - 2)
        u.es_yo = u.pk == request.user.pk
    params = {k: v for k, v in {**filtros, "por": "" if por == 25 else por}.items() if v not in ("", None)}
    volver = "?" + urlencode({**params, **({"pagina": num} if num > 1 else {})}) if params or num > 1 else ""
    conteos = _conteos()
    base = reverse("cuentas:admin_personas")
    return vista(
        request,
        "admin/usuarios/index.html",
        {
            "usuarios": usuarios,
            "total": total,
            "num_pagina": num,
            "paginas": paginas,
            "por": por,
            "por_opciones": POR_PAGINA,
            "filtros": filtros,
            "pestanas": [(k, t, conteos[k or "todos"], f"{base}?rol={k}" if k else base) for k, t in GRUPOS.items()],
            "especialidades": ajustes.nombres_especialidades(),
            "params": params,
            "volver": volver,
            "desde": (num - 1) * por + 1 if total else 0,
            "hasta": min(total, num * por),
            "base": base,
            "clases_rol": {"alumno": "chip-info", "docente": "chip-ok", "direccion": "chip-aviso", "admin": "chip-gris"},
        },
        titulo="Personas",
        sub="Docentes, alumnos y personal",
        menu="usuarios",
    )


# ===================================================================== Acciones sobre varias personas


@require_POST
@exigir(Rol.ADMIN)
def lote(request):
    """Acciones sobre varias personas a la vez: activar, desactivar, dar contraseña nueva o eliminar."""
    yo = request.user
    volver = reverse("cuentas:admin_personas") + _consulta_volver(request)
    ids = _ids(request)
    accion = request.POST.get("accion", "").strip()
    if not ids:
        error(request, "Marca primero a las personas a las que quieres aplicar la acción.")
        return redirect(volver)
    if accion not in ("desactivar", "activar", "clave", "eliminar"):
        error(request, "Elige qué quieres hacer con las personas marcadas.")
        return redirect(volver)
    if accion == "eliminar":
        return _eliminar_cuentas(request, ids, volver, confirmado=False)  # siempre se muestra primero qué pasará
    hechos, claves = 0, []
    for u in Usuario.objects.filter(pk__in=ids).exclude(
        pk=yo.pk
    ):  # nadie se desactiva ni se cambia la clave a sí mismo desde aquí
        if accion == "clave":
            clave = clave_segura()
            u.dar_clave(clave, forzar=True)
            claves.append(
                {"nombre": u.nombre_completo, "usuario": u.correo or u.dni or "", "clave": clave, "telefono": u.telefono or ""}
            )
        else:
            u.is_active = accion == "activar"
            u.save(update_fields=["is_active"])
        hechos += 1
    if accion == "clave":
        Registro.anotar(
            yo, "clave", f"{yo.nombre_completo} dio contraseña nueva a {plural(hechos, 'persona', 'personas')}.", request
        )
        request.session["_claves_lote"] = claves
        return redirect("cuentas:admin_claves")
    activar = accion == "activar"
    Registro.anotar(
        yo,
        "cuenta",
        f"{yo.nombre_completo} {'activó' if activar else 'desactivó'} {plural(hechos, 'cuenta', 'cuentas')}.",
        request,
    )
    ok(
        request,
        plural(
            hechos,
            "cuenta activada" if activar else "cuenta desactivada",
            "cuentas activadas" if activar else "cuentas desactivadas",
        )
        + ".",
    )
    return redirect(volver)


# ===================================================================== Eliminar de verdad


def motivo_no_eliminar(persona):
    """Por qué NO se puede eliminar a esta persona (o None si se puede): solo un docente con módulos a su cargo."""
    n = persona.modulos_a_cargo.count()
    return f"Tiene a su cargo {plural(n, 'módulo', 'módulos')}: cámbiales el docente o elimínalos primero." if n else None


@require_POST
@exigir(Rol.ADMIN)
def eliminar(request):
    """Eliminar una o varias cuentas (botón de la fila): primero se muestra qué pasará; con «Sí, eliminar» se borra."""
    volver = reverse("cuentas:admin_personas") + _consulta_volver(request)
    ids = _ids(request)
    if not ids:
        error(request, "Marca primero a las personas que quieres eliminar.")
        return redirect(volver)
    return _eliminar_cuentas(request, ids, volver, confirmado="confirmado" in request.POST)


def _eliminar_cuentas(request, ids, volver, confirmado, mensaje_error=None):
    """«Eliminar» borra de verdad la cuenta y todo lo que hizo en el aula (trabajos, asistencia, tests, mensajes…). Por eso siempre
    se muestra antes qué se va a perder y, si hay algo, hay que marcar «Entiendo». No se elimina a uno mismo ni a un docente que
    todavía tiene módulos a su cargo (primero se le cambia el docente al módulo o se elimina el módulo)."""
    yo = request.user
    personas_ = {u.pk: u for u in Usuario.objects.filter(pk__in=ids[:MAX_ELIMINAR])}
    lista = []
    for pk in ids[:MAX_ELIMINAR]:
        u = personas_.get(pk)
        if u is None:
            continue
        motivo = "Es tu propia cuenta." if pk == yo.pk else motivo_no_eliminar(u)
        lista.append(
            {
                "persona": u,
                "motivo": motivo,
                "modulos": list(u.modulos_a_cargo.all()) if motivo and pk != yo.pk else [],
                "resumen": resumen.resumen_al_eliminar(u) if motivo is None else [],
                "inscripciones": u.matriculas.count() if motivo is None else 0,
            }
        )
    if not lista:
        error(request, "No se encontró a las personas que marcaste.")
        return redirect(volver)
    # Quitarla de un módulo no pide «Entiendo»; perder trabajos o mensajes, sí
    con_datos = any(f["motivo"] is None and f["resumen"] for f in lista)
    if confirmado and con_datos and "entiendo" not in request.POST:
        mensaje_error, confirmado = "Marca la casilla «Entiendo» para poder eliminar.", False
    if not confirmado:
        consulta = _consulta_volver(request)
        borrables = [f for f in lista if f["motivo"] is None]
        for f in lista:
            f["inscripciones_texto"] = ", ".join(
                x
                for x in [
                    f"su inscripción en {plural(f['inscripciones'], 'módulo', 'módulos')}" if f["inscripciones"] > 0 else "",
                    *f["resumen"],
                ]
                if x
            )
        return vista(
            request,
            "admin/usuarios/eliminar.html",
            {
                "borrables": borrables,
                "bloqueadas": [f for f in lista if f["motivo"] is not None],
                "consulta": consulta,
                "con_datos": con_datos,
                "error": mensaje_error,
                "url_lista": reverse("cuentas:admin_personas") + consulta,
            },
            titulo="Eliminar cuentas",
            sub="Revisa antes de borrar",
            volver=volver,
            menu="usuarios",
        )
    borradas = quedan = 0
    for f in lista:
        u = f["persona"]
        if f["motivo"] is not None:
            quedan += 1
            continue
        nombre, rol_texto = u.nombre_completo, Rol(u.rol).label
        try:
            with transaction.atomic():
                u.delete()  # los archivos subidos se borran cuando la base ya quedó bien
        except ProtectedError:
            quedan += 1
            continue
        borradas += 1
        perdido = f" Se borró también: {', '.join(f['resumen'])}." if f["resumen"] else ""
        Registro.anotar(yo, "cuenta", f"{yo.nombre_completo} eliminó la cuenta de {nombre} ({rol_texto}).{perdido}", request)
    mensaje = plural(borradas, "cuenta eliminada", "cuentas eliminadas") + "." if borradas else "No se eliminó ninguna cuenta."
    if quedan:
        mensaje += (
            f" {plural(quedan, 'no se pudo eliminar', 'no se pudieron eliminar')} (revisa que no tengan módulos a su cargo)."
        )
    (ok if borradas else error)(request, mensaje)
    return redirect(volver)


# ===================================================================== Contraseñas nuevas


@exigir(Rol.ADMIN)
def claves_lote(request):
    """Contraseñas nuevas dadas en lote. Se muestran una sola vez."""
    lista = request.session.pop("_claves_lote", None)
    if not lista:
        error(request, "No hay contraseñas nuevas para mostrar.")
        return redirect("cuentas:admin_personas")
    texto = "".join(f"{x['nombre']} · Usuario: {x['usuario']} · Contraseña: {x['clave']}\n" for x in lista)
    entra_en = url_absoluta(request, reverse("cuentas:login"))
    for x in lista:
        mensaje = (
            f"Aula virtual del {ajustes.ajuste('centro_nombre')}\nEntra en: {entra_en}\nUsuario: {x['usuario']}\n"
            f"Contraseña: {x['clave']}\nAl entrar por primera vez te pedirá elegir tu propia contraseña."
        )
        x["wa"] = (whatsapp_url(x.get("telefono")) or "https://wa.me/") + "?text=" + quote(mensaje, safe="")
    return vista(
        request,
        "admin/usuarios/claves.html",
        {"lista": lista, "texto_todo": texto},
        titulo="Contraseñas nuevas",
        sub="Se muestran una sola vez",
        volver=url_o_numeral("cuentas:admin_personas"),
        menu="usuarios",
    )


# ===================================================================== Crear y editar


def _entrada(request, clave, defecto=""):
    return (request.POST.get(clave) or defecto).strip()


def _fecha(texto):
    """Fecha AAAA-MM-DD válida, o None."""
    try:
        return date.fromisoformat(texto) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto or "") else None
    except ValueError:
        return None


def _datos(request):
    rol = _entrada(request, "rol", "alumno")
    correo = _entrada(request, "correo")[:120].lower()
    if correo and "@" not in correo:
        correo += "@" + ajustes.ajuste("dominio_correo")  # «profesortecnico» → profesortecnico@cetpro.com
    return {
        "dni": re.sub(r"\D", "", _entrada(request, "dni")),
        "nombres": _entrada(request, "nombres")[:100],
        "apellidos": _entrada(request, "apellidos")[:100],
        "correo": correo,
        "telefono": re.sub(r"[^\d+ ]", "", _entrada(request, "telefono"))[:15],
        "rol": rol if rol in Rol.values else Rol.ALUMNO,
    }


def _validar(request, d, volver, excluir=None):
    """Revisa los datos de una persona. Devuelve una redirección con el error, o None si todo está bien."""
    # El alumno SIEMPRE entra con su DNI (el correo es opcional). Las demás cuentas necesitan al menos el correo o el DNI.
    if d["rol"] == Rol.ALUMNO and d["dni"] == "":
        return volver_con_error(request, volver, "El alumno entra con su DNI: escribe los 8 números.")
    if d["correo"] == "" and d["dni"] == "":
        return volver_con_error(
            request,
            volver,
            f"Escribe el correo (por ejemplo profesorpeluqueria@{ajustes.ajuste('dominio_correo')}) o el DNI para que pueda entrar.",
        )
    if d["dni"] != "" and len(d["dni"]) != 8:
        return volver_con_error(request, volver, "El DNI debe tener 8 números.")
    if d["nombres"] == "" or d["apellidos"] == "":
        return volver_con_error(request, volver, "Escribe los nombres y apellidos.")
    if d["correo"]:
        try:
            validate_email(d["correo"])
        except ValidationError:
            return volver_con_error(request, volver, "El correo no es válido. Ejemplo: profesorpeluqueria@cetpro.com")
    repetidos = Q(pk__in=[])
    if d["dni"]:
        repetidos |= Q(dni=d["dni"])
    if d["correo"]:
        repetidos |= Q(correo__iexact=d["correo"])
    consulta = Usuario.objects.filter(repetidos)
    if excluir is not None:
        consulta = consulta.exclude(pk=excluir)
    if consulta.exists():
        return volver_con_error(request, volver, f"Ya existe {'otra' if excluir else 'una'} persona con ese correo o DNI.")
    return None


def _modulos_para_inscribir():
    return Modulo.objects.activos().select_related("docente").order_by("especialidad", "modulo", "nombre")


def _etiqueta_de_modulo(m):
    """«Peluquería · Módulo 1 · mañana · Prof. Torres», con el nombre entre comillas si no es el de siempre."""
    propio = f" · «{m.nombre}»" if m.nombre != f"{m.especialidad} – {m.modulo}" else ""
    return f"{m.especialidad} · {m.modulo or m.nombre}{propio} · {m.turno} · Prof. {m.docente.apellidos}"


@exigir(Rol.ADMIN)
def nueva(request):
    rol = request.GET.get("rol", "")
    modulos = list(_modulos_para_inscribir())
    old = request.session.get("_old", {})
    marcados = {int(x) for x in old.get("modulos[]", []) if str(x).isdigit()}
    return vista(
        request,
        "admin/usuarios/form.html",
        {
            "persona": None,
            "roles": Rol.choices,
            "rol_actual": old.get("rol") or (rol if rol in Rol.values else Rol.DOCENTE),
            "v": {c: old.get(c, "") for c in ("nombres", "apellidos", "correo", "dni", "telefono")},
            "modulos_activos": [(m, _etiqueta_de_modulo(m), m.pk in marcados) for m in modulos],
            "forzar_marcado": ("forzar_cambio" in old) if old else True,
            "dominio": ajustes.ajuste("dominio_correo"),
            "fecha_nacimiento": old.get("fecha_nacimiento", ""),
        },
        titulo="Nueva persona",
        volver=reverse("cuentas:admin_personas"),
        menu="usuarios",
    )


@require_POST
@exigir(Rol.ADMIN)
def guardar(request):
    yo = request.user
    volver = reverse("cuentas:admin_nueva_persona")
    d = _datos(request)
    falla = _validar(request, d, volver)
    if falla:
        return falla
    propia = request.POST.get("clave", "")
    forzar = "forzar_cambio" in request.POST
    if propia == "":
        # Sin contraseña escrita: una segura al azar (nunca el DNI: lo conoce mucha gente y alguien podría entrar antes que la
        # persona). Como no la eligió ella, siempre la cambia al entrar.
        d["clave"], forzar = clave_segura(), True
    elif len(propia) < 6:
        return volver_con_error(request, volver, "La contraseña debe tener al menos 6 caracteres.")
    else:
        d["clave"] = propia
    try:
        with transaction.atomic():
            persona = Usuario.objects.create_user(
                correo=d["correo"] or None,
                password=d["clave"],
                rol=d["rol"],
                nombres=d["nombres"],
                apellidos=d["apellidos"],
                dni=d["dni"] or None,
                telefono=d["telefono"],
                fecha_nacimiento=_fecha(_entrada(request, "fecha_nacimiento")),
                origen=Origen.ADMIN,
                debe_cambiar_clave=forzar,
                activado=timezone.now(),
            )
    except IntegrityError:
        return volver_con_error(request, volver, "Ya existe una persona con ese correo o DNI.")
    matriculados = 0
    if d["rol"] == Rol.ALUMNO:
        ids = [int(x) for x in request.POST.getlist("modulos[]") if x.isdigit()]
        for m in Modulo.objects.activos().filter(pk__in=ids):
            matriculados += 1 if m.matricular(persona) else 0
    Registro.anotar(
        yo,
        "cuenta",
        f"{yo.nombre_completo} creó la cuenta de {d['nombres']} {d['apellidos']} ({Rol(d['rol']).label})"
        + (f" y la inscribió en {plural(matriculados, 'módulo', 'módulos')}" if matriculados else "")
        + ".",
        request,
    )
    request.session["_clave_otro"] = {
        "nombre": f"{d['nombres']} {d['apellidos']}",
        "usuario": d["correo"] or d["dni"],
        "clave": d["clave"],
        "telefono": d["telefono"],
        "forzar": forzar,
    }
    ok(
        request,
        f"Cuenta creada: {d['nombres']} {d['apellidos']}"
        + (f" · {plural(matriculados, 'módulo', 'módulos')}." if matriculados else "."),
    )
    return redirect("cuentas:admin_personas")


@exigir(Rol.ADMIN)
def editar(request, id):
    persona = Usuario.objects.filter(pk=id).first()
    if persona is None:
        return no_encontrado(request)
    old = request.session.get("_old", {})
    if persona.rol == Rol.ALUMNO:
        cursos = Modulo.objects.de_alumno(persona).order_by("nombre")
    elif persona.rol == Rol.DOCENTE:
        cursos = Modulo.objects.de_docente(persona).order_by("nombre")
    else:
        cursos = []
    return vista(
        request,
        "admin/usuarios/form.html",
        {
            "persona": persona,
            "roles": Rol.choices,
            "rol_actual": old.get("rol") or persona.rol,
            "v": {c: old.get(c, getattr(persona, c, "") or "") for c in ("nombres", "apellidos", "correo", "dni", "telefono")},
            "cursos": cursos,
            "dominio": ajustes.ajuste("dominio_correo"),
            "fecha_nacimiento": old.get(
                "fecha_nacimiento", persona.fecha_nacimiento.isoformat() if persona.fecha_nacimiento else ""
            ),
            "es_yo": persona.pk == request.user.pk,
        },
        titulo="Editar persona",
        sub=persona.nombre_completo,
        volver=reverse("cuentas:admin_personas"),
        menu="usuarios",
    )


@require_POST
@exigir(Rol.ADMIN)
def actualizar(request, id):
    yo = request.user
    antes = Usuario.objects.filter(pk=id).first()
    if antes is None:
        return no_encontrado(request)
    volver = reverse("cuentas:admin_editar_persona", args=[id])
    d = _datos(request)
    if id == yo.pk:
        d["rol"] = Rol.ADMIN  # nadie se quita a sí mismo el rol de administrador
    falla = _validar(request, d, volver, excluir=id)
    if falla:
        return falla
    nombre_antes = antes.nombre_completo
    antes.dni, antes.nombres, antes.apellidos = d["dni"] or None, d["nombres"], d["apellidos"]
    antes.correo, antes.telefono, antes.rol = d["correo"] or None, d["telefono"], d["rol"]
    nacimiento = _fecha(_entrada(request, "fecha_nacimiento"))
    if nacimiento:
        antes.fecha_nacimiento = nacimiento
    try:
        with transaction.atomic():
            antes.save()
    except IntegrityError:
        return volver_con_error(request, volver, "Ya existe otra persona con ese correo o DNI.")
    Registro.anotar(yo, "cuenta", f"{yo.nombre_completo} editó los datos de {nombre_antes}.", request)
    ok(request, "Cambios guardados.")
    return redirect("cuentas:admin_personas")


@require_POST
@exigir(Rol.ADMIN)
def clave(request, id):
    """Le da una contraseña nueva y la muestra una sola vez. Si la pone el administrador, la persona la cambia al entrar."""
    yo = request.user
    persona = Usuario.objects.filter(pk=id).first()
    if persona is None:
        return no_encontrado(request)
    desde_lista = request.POST.get("desde") == "lista"
    volver = (
        reverse("cuentas:admin_personas") + _consulta_volver(request)
        if desde_lista
        else reverse("cuentas:admin_editar_persona", args=[id])
    )
    propia = request.POST.get("clave", "")
    if propia != "" and len(propia) < 6:
        return volver_con_error(request, volver, "La contraseña debe tener al menos 6 caracteres.")
    forzar = propia == "" or "forzar_cambio" in request.POST or desde_lista
    nueva_clave = propia if propia != "" else clave_segura()
    persona.dar_clave(nueva_clave, forzar=forzar)
    Registro.anotar(yo, "clave", f"{yo.nombre_completo} cambió la contraseña de {persona.nombre_completo}.", request)
    request.session["_clave_otro"] = {
        "nombre": persona.nombre_completo,
        "usuario": persona.correo or persona.dni or "",
        "clave": nueva_clave,
        "telefono": persona.telefono or "",
        "forzar": forzar,
    }
    return redirect(volver)


@require_POST
@exigir(Rol.ADMIN)
def estado(request, id):
    """Activa o desactiva una cuenta (no se borra nada: «Eliminar» es otro botón)."""
    yo = request.user
    if id == yo.pk:
        error(request, "No puedes desactivar tu propia cuenta.")
        return redirect("cuentas:admin_personas")
    persona = Usuario.objects.filter(pk=id).first()
    if persona is None:
        return no_encontrado(request)
    desde_lista = request.POST.get("desde") == "lista"
    volver = (
        reverse("cuentas:admin_personas") + _consulta_volver(request)
        if desde_lista
        else reverse("cuentas:admin_editar_persona", args=[id])
    )
    activa = persona.is_active
    persona.is_active = not activa
    persona.save(update_fields=["is_active"])
    Registro.anotar(
        yo,
        "cuenta",
        f"{yo.nombre_completo} {'desactivó' if activa else 'activó'} la cuenta de {persona.nombre_completo}.",
        request,
    )
    ok(request, "Estado actualizado.")
    return redirect(volver)


personas_o_guardar = por_metodo(GET=personas, POST=guardar)
