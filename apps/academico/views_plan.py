"""Cargar el plan de estudios (el Excel del Ministerio) para llenar solos los módulos y sus unidades didácticas.

Paso 1: se sube el archivo. Paso 2: se revisa lo que se encontró. Paso 3: se crean los módulos (o se completan los que ya existen).
Lo usan el administrador (cualquier curso y docente) y el docente (solo sus módulos)."""

from django.conf import settings
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.cuentas.models import Rol, Usuario
from apps.nucleo import ajustes, importador
from apps.nucleo.models import Registro
from apps.nucleo.permisos import exigir
from apps.nucleo.utils import error, ok, plural, por_metodo, vista, volver_con_error

from . import plan_estudios
from .models import Modulo, UnidadDidactica

COLOR_CURSO = "#1249A3"  # color con el que se crea un curso nuevo (oscuro, se lee con letra blanca)
TURNOS = [("mañana", "Mañana"), ("tarde", "Tarde"), ("noche", "Noche")]


def _entrada(request, clave, defecto=""):
    return (request.POST.get(clave) or defecto).strip()


def _volver_y_menu(request):
    return ("admin_cursos", "admin-cursos") if request.user.rol == Rol.ADMIN else ("modulos", "cursos")


@exigir(Rol.ADMIN, Rol.DOCENTE)
def subir(request):
    """Paso 1: subir el Excel del plan de estudios."""
    ruta, menu = _volver_y_menu(request)
    return vista(
        request,
        "plan/subir.html",
        {},
        titulo="Cargar plan de estudios",
        sub="Se llenan solos los módulos y sus unidades",
        volver=reverse(f"academico:{ruta}"),
        menu=menu,
    )


@require_POST
@exigir(Rol.ADMIN, Rol.DOCENTE)
def leer(request):
    """Lee el archivo subido y pasa a la revisión."""
    destino = reverse("academico:plan")
    archivo = request.FILES.get("archivo")
    if archivo is None or archivo.size == 0:
        error(request, "Elige el archivo de Excel del plan de estudios.")
        return redirect(destino)
    if archivo.size > settings.ARCHIVOS_MAX_MB * 1024 * 1024:
        error(request, f"El archivo es muy pesado (máximo {settings.ARCHIVOS_MAX_MB} MB).")
        return redirect(destino)
    if not archivo.name.lower().endswith(".xlsx"):
        error(request, "Sube el plan de estudios como archivo de Excel (.xlsx).")
        return redirect(destino)
    try:
        plan = plan_estudios.leer(archivo)
    except importador.ImportadorError as ex:
        error(request, str(ex))
        return redirect(destino)
    request.session["_plan"] = plan
    return redirect("academico:plan_revisar")


def _curso_del_plan(nombre):
    """El curso de la lista que se llama igual que el del archivo (sin mirar mayúsculas ni tildes), o None."""
    n = importador.normalizar(nombre)
    for e in ajustes.nombres_especialidades():
        if n and importador.normalizar(e) == n:
            return e
    return None


def _plan_en_sesion(request):
    plan = request.session.get("_plan")
    return plan if isinstance(plan, dict) and plan.get("modulos") else None


@exigir(Rol.ADMIN, Rol.DOCENTE)
def revisar(request):
    """Paso 2: lo que se encontró en el Excel. Se elige qué módulos crear (o completar si ya existen)."""
    u = request.user
    plan = _plan_en_sesion(request)
    if plan is None:
        error(request, "Primero sube el archivo del plan de estudios.")
        return redirect("academico:plan")
    es_admin = u.rol == Rol.ADMIN
    old = request.session.get("_old", {})
    curso_sel = _curso_del_plan(plan["curso"])
    propios = Modulo.objects.activos() if es_admin else Modulo.objects.de_docente(u)
    existentes = list(propios.select_related("docente").order_by("nombre")) if curso_sel else []
    existentes = [m for m in existentes if m.especialidad == curso_sel]
    curso_elegido = old.get("curso") or curso_sel or ("__nuevo__" if es_admin and plan["curso"] else "")
    for i, m in enumerate(plan["modulos"]):
        m["i"] = i
        m["usar"] = (f"usar[{i}]" in old) if old else True
        m["destino"] = old.get(f"destino[{i}]", "")
        m["docente_sel"] = old.get(f"docente[{i}]", "")
        m["turno_sel"] = old.get(f"turno[{i}]", "")
        m["horario"] = old.get(f"horario[{i}]", "")
    ruta, menu = _volver_y_menu(request)
    return vista(
        request,
        "plan/revisar.html",
        {
            "plan": plan,
            "es_admin": es_admin,
            "curso_sel": curso_sel,
            "curso_elegido": curso_elegido,
            "especialidades": ajustes.nombres_especialidades(),
            "creditos": sum(m["creditos"] for m in plan["modulos"]),
            "horas": sum(m["horas"] for m in plan["modulos"]),
            "periodo": old.get("periodo", ajustes.ajuste("periodo")),
            "existentes": existentes,
            "docentes": list(Usuario.objects.docentes()) if es_admin else [],
            "turnos": TURNOS,
            "nuevo_posible": es_admin and bool(plan["curso"]) and curso_sel is None,
        },
        titulo="Revisar el plan",
        sub=plan["curso"] or "Elige el curso",
        volver=reverse("academico:plan"),
        menu=menu,
    )


@require_POST
@exigir(Rol.ADMIN, Rol.DOCENTE)
def crear(request):
    """Paso 3: crea los módulos marcados (con sus unidades) o completa los que ya existen.
    Primero se revisa todo y recién después se crea, para que nunca quede algo a medias."""
    yo = request.user
    es_admin = yo.rol == Rol.ADMIN
    plan = _plan_en_sesion(request)
    if plan is None:
        error(request, "El archivo ya no está cargado. Súbelo otra vez.")
        return redirect("academico:plan")
    volver = reverse("academico:plan_revisar")

    # El curso: uno de la lista o (solo el administrador) el que trae el archivo, que se crea al final
    curso = _entrada(request, "curso")
    crear_curso = False
    nombres = ajustes.nombres_especialidades()
    if curso == "__nuevo__" and es_admin and plan["curso"].strip():
        curso = plan["curso"].strip()
        crear_curso = curso not in nombres
    elif curso not in nombres:
        return volver_con_error(
            request,
            volver,
            "Elige el curso al que pertenece el plan."
            if es_admin
            else "Ese curso todavía no existe. Pídele al administrador que lo cree o que cargue el plan.",
        )
    periodo = _entrada(request, "periodo")[:20]

    # 1) Revisar cada módulo marcado y armar lo que se va a hacer
    acciones = []
    propios = None if es_admin else set(Modulo.objects.de_docente(yo).values_list("pk", flat=True))
    for i, m in enumerate(plan["modulos"]):
        if _entrada(request, f"usar[{i}]") == "":
            continue  # una casilla sin marcar no se envía
        unidades = [{"nombre": x["nombre"], "creditos": int(x["creditos"]), "horas": int(x["horas"])} for x in m["unidades"]]
        destino = _entrada(request, f"destino[{i}]", "nuevo")
        if destino != "nuevo":
            existente = Modulo.objects.filter(pk=int(destino)).first() if destino.isdigit() else None
            if existente is None or existente.especialidad != curso or (propios is not None and existente.pk not in propios):
                return volver_con_error(request, volver, f"Elige un módulo de tu lista para completar «{m['modulo']}».")
            acciones.append({"completar": existente, "unidades": unidades})
            continue
        turno = _entrada(request, f"turno[{i}]")
        if periodo == "" or turno not in dict(TURNOS):
            return volver_con_error(request, volver, f"Para crear «{m['modulo']}» escribe el periodo y elige el turno.")
        docente = yo
        if es_admin:
            docente_id = _entrada(request, f"docente[{i}]")
            docente = Usuario.objects.filter(pk=docente_id, rol=Rol.DOCENTE).first() if docente_id.isdigit() else None
            if docente is None:
                return volver_con_error(request, volver, f"Elige el docente de «{m['modulo']}».")
        acciones.append(
            {
                "crear": {
                    "nombre": (m["nombre"][:150] or f"{curso} – {m['modulo']}"),
                    "especialidad": curso,
                    "modulo": m["modulo"],
                    "periodo": periodo,
                    "turno": turno,
                    "docente": docente,
                    "horario": _entrada(request, f"horario[{i}]")[:120],
                },
                "unidades": unidades,
            }
        )
    if not acciones:
        return volver_con_error(request, volver, "Marca al menos un módulo para cargar.")

    # 2) Crear
    nuevos = completados = 0
    with transaction.atomic():
        if crear_curso:
            ajustes.guardar_especialidades([*ajustes.especialidades(), {"nombre": curso, "color": COLOR_CURSO, "foto": None}])
        for a in acciones:
            if "completar" in a:
                UnidadDidactica.guardar_lista(a["completar"], a["unidades"])
                completados += 1
            else:
                UnidadDidactica.guardar_lista(Modulo.crear(**a["crear"]), a["unidades"])
                nuevos += 1
    request.session.pop("_plan", None)
    Registro.anotar(
        yo,
        "modulo",
        f"{yo.nombre_completo} cargó el plan de estudios de «{curso}»: {plural(nuevos, 'módulo nuevo', 'módulos nuevos')} "
        f"y {plural(completados, 'completado', 'completados')}.",
        request,
    )
    partes = [
        x
        for x in (
            plural(nuevos, "módulo creado", "módulos creados") if nuevos else "",
            plural(completados, "módulo completado", "módulos completados") if completados else "",
        )
        if x
    ]
    ok(request, f"Plan cargado en «{curso}»: {' y '.join(partes)}.")
    return redirect("academico:admin_cursos" if es_admin else "academico:modulos")


subir_o_leer = por_metodo(GET=subir, POST=leer)
