"""Cargar una lista de alumnos (Excel, CSV o pegada). Quedan «pendientes» hasta que creen su contraseña con su DNI
(o reciben una temporal para enviarla por WhatsApp).

Solo se guarda lo necesario: DNI, nombres, apellidos, celular y fecha de nacimiento. Lo demás que traiga el Excel de la
inscripción (edad, dirección, estado civil…) se ignora."""

import re
from datetime import date, datetime, timedelta

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.academico.models import Modulo
from apps.nucleo import importador
from apps.nucleo.models import Registro
from apps.nucleo.permisos import exigir
from apps.nucleo.utils import clave_segura, plural, por_metodo, vista, volver_con_error

from .models import Origen, Rol, Usuario

MAX_FILAS = 2000
MAX_ERRORES = 50

# Títulos de columna que se reconocen (ya sin tildes ni mayúsculas)
COLUMNAS = {
    "dni": ["dni"],
    "nombres": ["nombres", "nombre"],
    "apellidos": ["apellidos", "apellido"],
    "paterno": ["apellidos paterno", "apellido paterno", "ape paterno", "ap paterno", "paterno"],
    "materno": ["apellidos materno", "apellido materno", "ape materno", "ap materno", "materno"],
    "celular": ["celular", "telefono", "cel", "telefono celular"],
    "nacimiento": ["fecha de nacimiento", "fecha nacimiento", "nacimiento", "fecha"],
    "codigo": ["codigo", "codigo del modulo", "modulo", "modulos"],
}
ROMANOS = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6}


def numeros_de_modulo(texto):
    """«1», «2», «1 y 2», «Módulo II»… → los números de módulo; None = todos los marcados; False = no se entiende."""
    t = importador.normalizar(texto)
    if re.search(r"\b(ambos|los dos|dos|todos)\b", t):
        return None
    numeros = [int(x) for x in re.findall(r"\d+", t)]
    if not numeros:
        numeros = [ROMANOS[x] for x in re.findall(r"\b(vi|iv|v|iii|ii|i)\b", t)]
    return numeros or False


def numero_del_modulo(nombre):
    """El número de un módulo según su nombre: «Módulo 2» o «Módulo II» → 2."""
    n = numeros_de_modulo(nombre)
    return n[0] if isinstance(n, list) and len(n) == 1 else None


def fecha_flexible(texto):
    """Acepta 25/03/1970, 1970-03-25, 25-03-1970 o el número de fecha de Excel."""
    if not texto:
        return None
    if texto.isdigit() and 3000 < int(texto) < 60000:
        return date(1899, 12, 30) + timedelta(days=int(texto))
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            d = datetime.strptime(texto, formato).date()
        except ValueError:
            continue
        if d.year > 1900:
            return d
    return None


def _columnas(filas):
    """Ubica las columnas por su título si la primera fila los trae; si no, por posición. Devuelve (columnas, filas de datos)."""
    col = {"dni": 0, "nombres": 1, "apellidos": 2, "celular": 3, "nacimiento": 4, "codigo": 5, "paterno": None, "materno": None}
    cabecera = [importador.normalizar(str(c)) for c in filas[0]]
    if "dni" not in cabecera:
        return col, filas
    for clave, nombres in COLUMNAS.items():
        col[clave] = next((cabecera.index(n) for n in nombres if n in cabecera), None)
    return col, filas[1:]


@exigir(Rol.ADMIN)
def importar(request):
    resultado = request.session.pop("_importacion", None)
    modulos = list(Modulo.objects.activos().select_related("docente").order_by("especialidad", "modulo", "nombre"))
    por_curso = {}
    for m in modulos:
        por_curso.setdefault(m.especialidad, []).append((m, _etiqueta_corta(m)))
    return vista(
        request,
        "admin/usuarios/importar.html",
        {"modulos": modulos, "por_curso": por_curso, "resultado": resultado if isinstance(resultado, dict) else None},
        titulo="Cargar alumnos",
        sub="Desde Excel o pegando una lista",
        volver=reverse("cuentas:admin_personas"),
        menu="usuarios",
    )


def _etiqueta_corta(m):
    """«Módulo 1 · «nombre» · mañana · Prof. Torres» (el curso ya está en el título del grupo)."""
    propio = f" · «{m.nombre}»" if m.nombre != f"{m.especialidad} – {m.modulo}" else ""
    return f"{m.modulo or m.nombre}{propio} · {m.turno} · Prof. {m.docente.apellidos}"


def leer_filas(request, volver):
    """Las filas de lo que subió o pegó el administrador (Excel, CSV o lista pegada). Devuelve (filas, None) o, si algo falla,
    (None, redirección con el mensaje de error). La usan la carga de alumnos y la de docentes."""
    filas = []
    archivo = request.FILES.get("archivo")
    if archivo is not None and archivo.size > 0:
        if archivo.size > settings.ARCHIVOS_MAX_MB * 1024 * 1024:
            return None, volver_con_error(
                request, volver, f"El archivo es muy pesado. El máximo es {settings.ARCHIVOS_MAX_MB} MB."
            )
        try:
            filas = importador.filas_tabla(archivo, archivo.name, max_filas=MAX_FILAS)
        except importador.ImportadorError as ex:
            return None, volver_con_error(request, volver, str(ex))
    else:
        for linea in request.POST.get("lista", "").splitlines():
            if linea.strip():
                filas.append([x.strip() for x in re.split(r"	|;|,", linea)])
    if not filas:
        return None, volver_con_error(request, volver, "No se encontró ninguna fila. Sube un Excel o pega la lista.")
    return filas, None


@require_POST
@exigir(Rol.ADMIN)
def procesar(request):
    yo = request.user
    volver = reverse("cuentas:admin_importar")
    filas, falla = leer_filas(request, volver)
    if falla:
        return falla

    # Módulos en los que se inscribe a todos: los marcados en la pantalla (uno o dos)
    ids = [int(x) for x in request.POST.getlist("curso_id[]") + request.POST.getlist("curso_id") if x.isdigit()]
    marcados = list(Modulo.objects.activos().filter(pk__in=ids).order_by("nombre"))
    con_clave = "con_clave" in request.POST

    col, filas = _columnas(filas)

    def leer(fila, clave):
        i = col[clave]
        return "" if i is None or i >= len(fila) else str(fila[i]).strip()

    nuevos = inscritos = 0
    errores, claves = [], []
    for n, fila in enumerate(filas, start=1):
        linea = f"Fila {n}"
        dni = re.sub(r"\D", "", leer(fila, "dni"))
        if dni == "" and leer(fila, "nombres") == "":
            continue  # fila vacía
        if len(dni) == 7:
            dni = "0" + dni  # Excel quita el 0 inicial
        if len(dni) != 8:
            errores.append(f"{linea}: el DNI debe tener 8 números.")
            continue

        # ¿En qué módulos va esta fila? Por defecto, en todos los marcados. La columna «módulo» puede decir 1, 2, «1 y 2»
        # (de entre los marcados) o traer uno o más códigos de módulo (PEL-4821).
        destinos = marcados
        celda = leer(fila, "codigo")
        if celda:
            codigos = re.findall(r"[A-Za-z]{3}[-\s]?\d{4}", celda)
            if codigos:
                destinos = []
                for codigo in codigos:
                    por_codigo = Modulo.por_codigo(codigo)
                    if por_codigo is None:
                        errores.append(f"{linea}: no existe el módulo con código «{codigo}».")
                        destinos = None
                        break
                    destinos.append(por_codigo)
                if destinos is None:
                    continue
            else:
                numeros = numeros_de_modulo(celda)
                if numeros is False:
                    errores.append(f"{linea}: no entendí el módulo «{celda}» (escribe 1, 2 o «1 y 2»).")
                    continue
                if numeros is not None:
                    destinos = [m for m in marcados if numero_del_modulo(m.modulo) in numeros]
                    if not destinos:
                        errores.append(f"{linea}: marca arriba el módulo «{celda}» para poder inscribirlo.")
                        continue

        u = Usuario.objects.filter(dni=dni).first()
        celular = re.sub(r"\D", "", leer(fila, "celular"))
        if u is None:
            nombres = leer(fila, "nombres").lower().title()
            apellidos = leer(fila, "apellidos") or f"{leer(fila, 'paterno')} {leer(fila, 'materno')}".strip()
            apellidos = apellidos.lower().title()
            if nombres == "" or apellidos == "":
                errores.append(f"{linea}: falta el nombre o el apellido (DNI {dni}).")
                continue
            u = Usuario.objects.crear_alumno(
                dni,
                nombres[:100],
                apellidos[:100],
                origen=Origen.LISTA,
                telefono=celular if len(celular) == 9 else "",
                fecha_nacimiento=fecha_flexible(leer(fila, "nacimiento")),
            )
            nuevos += 1
        elif u.rol != Rol.ALUMNO:
            errores.append(f"{linea}: el DNI {dni} es de un {Rol(u.rol).label.lower()}.")
            continue
        for m in destinos:
            inscritos += 1 if m.matricular(u) else 0
        # Contraseña temporal para enviarla por WhatsApp: solo a quien todavía no tiene (la cambia al entrar)
        if con_clave and u.pendiente:
            clave = clave_segura()
            u.dar_clave(clave, forzar=True)
            claves.append(
                {
                    "nombre": u.nombre_completo,
                    "usuario": dni,
                    "clave": clave,
                    "telefono": u.telefono or (celular if len(celular) == 9 else ""),
                }
            )
    if claves:
        request.session["_claves_lote"] = claves
    request.session["_importacion"] = {
        "nuevos": nuevos,
        "inscritos": inscritos,
        "claves": len(claves),
        "errores": errores[:MAX_ERRORES],
    }
    Registro.anotar(
        yo,
        "cuenta",
        f"{yo.nombre_completo} cargó una lista: {plural(nuevos, 'alumno nuevo', 'alumnos nuevos')}, "
        f"{plural(inscritos, 'inscripción', 'inscripciones')}"
        + (f" y {plural(len(claves), 'contraseña temporal', 'contraseñas temporales')}" if claves else "")
        + ".",
        request,
    )
    return redirect("cuentas:admin_importar")


importar_o_procesar = por_metodo(GET=importar, POST=procesar)
