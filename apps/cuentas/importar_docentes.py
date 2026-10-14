"""Cargar una lista de docentes (Excel, CSV o pegada). Cada docente nuevo recibe una contraseña temporal, que se muestra una
sola vez para enviársela por WhatsApp; la cambia por una propia la primera vez que entra.

Solo se guarda lo necesario: nombres, apellidos, correo (con el que entra), DNI (opcional) y celular. Lo demás que traiga el
Excel se ignora. Los módulos se asignan después, al crearlos (cada módulo lleva su docente)."""

import re
import unicodedata

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.nucleo import ajustes, importador
from apps.nucleo.models import Registro
from apps.nucleo.permisos import exigir
from apps.nucleo.utils import clave_segura, plural, por_metodo, vista, volver_con_error

from .importar_alumnos import MAX_ERRORES, leer_filas
from .models import Origen, Rol, Usuario

# Títulos de columna que se reconocen (ya sin tildes ni mayúsculas)
COLUMNAS = {
    "nombres": ["nombres", "nombre"],
    "apellidos": ["apellidos", "apellido"],
    "paterno": ["apellidos paterno", "apellido paterno", "ape paterno", "ap paterno", "paterno"],
    "materno": ["apellidos materno", "apellido materno", "ape materno", "ap materno", "materno"],
    "correo": ["correo", "correo electronico", "email", "e-mail", "correo institucional", "correo del aula"],
    "dni": ["dni", "documento"],
    "celular": ["celular", "telefono", "cel", "telefono celular"],
}
# Sin títulos, las columnas van en este orden
POSICION = {"nombres": 0, "apellidos": 1, "correo": 2, "dni": 3, "celular": 4, "paterno": None, "materno": None}

ENCABEZADO_MODELO = ["Nombres", "Apellidos", "Correo", "DNI", "Celular"]


def _columnas(filas):
    """Ubica las columnas por su título si la primera fila los trae; si no, por posición. Devuelve (columnas, filas de datos, ¿trae títulos?)."""
    cabecera = [importador.normalizar(str(c)) for c in filas[0]]
    conocidos = {n for nombres in COLUMNAS.values() for n in nombres}
    if not any(c in conocidos for c in cabecera):
        return dict(POSICION), filas, False
    col = {clave: next((cabecera.index(n) for n in nombres if n in cabecera), None) for clave, nombres in COLUMNAS.items()}
    return col, filas[1:], True


def _sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _slug(texto):
    return re.sub(r"[^a-z0-9]", "", _sin_tildes(texto).lower())


def correo_para(nombres, apellidos):
    """Un correo libre con el estilo del aula: «Rosa Elena» «Paredes Huamán» → rosa.paredes@cetpro.com (rosa.paredes2@… si ya está)."""
    dominio = ajustes.ajuste("dominio_correo")
    base = f"{_slug(nombres.split()[0])}.{_slug(apellidos.split()[0])}".strip(".") or "docente"
    candidato, n = f"{base}@{dominio}", 1
    while Usuario.objects.filter(correo__iexact=candidato).exists():
        n += 1
        candidato = f"{base}{n}@{dominio}"
    return candidato


def _celular(texto):
    n = re.sub(r"\D", "", texto or "")
    if len(n) == 11 and n.startswith("51"):
        n = n[2:]  # +51 987 654 321
    return n if len(n) == 9 else ""


@exigir(Rol.ADMIN)
def importar(request):
    resultado = request.session.pop("_importacion_docentes", None)
    return vista(
        request,
        "admin/usuarios/importar_docentes.html",
        {
            "resultado": resultado if isinstance(resultado, dict) else None,
            "dominio": ajustes.ajuste("dominio_correo"),
            "encabezado": ENCABEZADO_MODELO,
        },
        titulo="Cargar docentes",
        sub="Desde Excel o pegando una lista",
        volver=reverse("cuentas:admin_personas"),
        menu="usuarios",
    )


@require_POST
@exigir(Rol.ADMIN)
def procesar(request):
    yo = request.user
    volver = reverse("cuentas:admin_importar_docentes")
    filas, falla = leer_filas(request, volver)
    if falla:
        return falla
    col, filas, con_titulos = _columnas(filas)
    if con_titulos and col["nombres"] is None:
        return volver_con_error(request, volver, "No encuentro la columna «Nombres». Revisa los títulos de la primera fila.")
    if con_titulos and col["apellidos"] is None and col["paterno"] is None:
        return volver_con_error(request, volver, "No encuentro la columna «Apellidos». Revisa los títulos de la primera fila.")

    def leer(fila, clave):
        i = col[clave]
        return "" if i is None or i >= len(fila) else str(fila[i]).strip()

    dominio = ajustes.ajuste("dominio_correo")
    nuevos = existentes = 0
    errores, claves = [], []
    for n, fila in enumerate(filas, start=1):
        linea = f"Fila {n}"
        if not any(str(c).strip() for c in fila):
            continue  # fila vacía
        nombres = leer(fila, "nombres").lower().title()[:100]
        apellidos = (leer(fila, "apellidos") or f"{leer(fila, 'paterno')} {leer(fila, 'materno')}".strip()).lower().title()[:100]
        if nombres == "" or apellidos == "":
            errores.append(f"{linea}: falta el nombre o el apellido.")
            continue

        dni = re.sub(r"\D", "", leer(fila, "dni"))
        if len(dni) == 7:
            dni = "0" + dni  # Excel quita el 0 inicial
        if dni and len(dni) != 8:
            errores.append(f"{linea} ({nombres} {apellidos}): el DNI debe tener 8 números.")
            continue

        correo = leer(fila, "correo")[:120].lower()
        if correo and "@" not in correo:
            correo += "@" + dominio  # «rosaparedes» → rosaparedes@cetpro.com
        if correo:
            try:
                validate_email(correo)
            except ValidationError:
                errores.append(f"{linea} ({nombres} {apellidos}): el correo «{correo}» no es válido.")
                continue

        # ¿Ya está en el aula? Por correo o DNI (o, si no trae ninguno, por nombre completo): así se puede volver a cargar la misma lista
        iguales = Q(pk__in=[])
        if correo:
            iguales |= Q(correo__iexact=correo)
        if dni:
            iguales |= Q(dni=dni)
        if not correo and not dni:
            iguales |= Q(rol=Rol.DOCENTE, nombres__iexact=nombres, apellidos__iexact=apellidos)
        ya_esta = Usuario.objects.filter(iguales).first()
        if ya_esta is not None:
            if ya_esta.rol == Rol.DOCENTE:
                existentes += 1
            else:
                errores.append(
                    f"{linea} ({nombres} {apellidos}): ese correo o DNI ya pertenece a otra persona ({Rol(ya_esta.rol).label.lower()})."
                )
            continue

        clave = clave_segura()
        celular = _celular(leer(fila, "celular"))
        try:
            with transaction.atomic():
                creado = Usuario.objects.create_user(
                    correo=correo or correo_para(nombres, apellidos),
                    password=clave,
                    rol=Rol.DOCENTE,
                    nombres=nombres,
                    apellidos=apellidos,
                    dni=dni or None,
                    telefono=celular,
                    origen=Origen.LISTA,
                    debe_cambiar_clave=True,  # la contraseña la eligió el aula, no ella: la cambia al entrar
                    activado=timezone.now(),
                )
        except IntegrityError:
            errores.append(f"{linea} ({nombres} {apellidos}): ya existe una persona con ese correo o DNI.")
            continue
        nuevos += 1
        claves.append({"nombre": creado.nombre_completo, "usuario": creado.correo, "clave": clave, "telefono": celular})

    if claves:
        request.session["_claves_lote"] = claves
    request.session["_importacion_docentes"] = {
        "nuevos": nuevos,
        "existentes": existentes,
        "claves": len(claves),
        "errores": errores[:MAX_ERRORES],
        "mas_errores": max(0, len(errores) - MAX_ERRORES),
    }
    Registro.anotar(
        yo,
        "cuenta",
        f"{yo.nombre_completo} cargó una lista de docentes: {plural(nuevos, 'docente nuevo', 'docentes nuevos')}"
        + (f" y {plural(existentes, 'ya estaba', 'ya estaban')}" if existentes else "")
        + ".",
        request,
    )
    return redirect("cuentas:admin_importar_docentes")


importar_o_procesar = por_metodo(GET=importar, POST=procesar)


def _modelo(nombre_archivo, encabezado):
    """Un CSV solo con los títulos de las columnas, para abrirlo en Excel y llenarlo."""
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    respuesta.write("\ufeff" + ";".join(encabezado) + "\r\n")
    return respuesta


@exigir(Rol.ADMIN)
def modelo_docentes(request):
    return _modelo("modelo-lista-de-docentes.csv", ENCABEZADO_MODELO)


@exigir(Rol.ADMIN)
def modelo_alumnos(request):
    return _modelo(
        "modelo-lista-de-alumnos.csv",
        ["Apellidos paterno", "Apellidos materno", "Nombres", "DNI", "Teléfono", "Fecha de nacimiento", "Módulo"],
    )
