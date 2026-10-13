"""Menú principal según el rol, con los números de pendientes (las otras apps registran sus contadores)."""

from django.urls import reverse

# clave del contador → función(usuario) → número. Las apps lo llenan en `ready()`.
CONTADORES = {}


def registrar_contador(clave, funcion):
    CONTADORES[clave] = funcion


def contar(clave, usuario):
    funcion = CONTADORES.get(clave)
    return int(funcion(usuario)) if funcion else 0


def url_o_numeral(nombre):
    """Dirección de una ruta; si esa parte del aula todavía no existe, devuelve '#'."""
    from django.urls import NoReverseMatch

    try:
        return reverse(nombre)
    except NoReverseMatch:
        return "#"


def menu_de(usuario):
    """Lista de (clave, dirección, texto, ícono, pendientes)."""
    if not usuario.is_authenticated:
        return []
    c = lambda clave: contar(clave, usuario)  # noqa: E731
    if usuario.rol == "alumno":
        filas = [
            ("inicio", "nucleo:inicio", "Inicio", "inicio", c("inicio")),
            ("cursos", "academico:modulos", "Mis módulos", "cursos", 0),
            ("notas", "academico:mis_notas", "Mis notas", "notas", 0),
            ("mensajes", "mensajes:index", "Mensajes", "mensaje", c("mensajes")),
            ("cuenta", "cuentas:cuenta", "Mi cuenta", "cuenta", 0),
        ]
    elif usuario.rol == "docente":
        filas = [
            ("inicio", "nucleo:inicio", "Inicio", "inicio", 0),
            ("cursos", "academico:modulos", "Mis módulos", "cursos", 0),
            ("calificar", "academico:por_calificar", "Por calificar", "calificar", c("calificar")),
            ("mensajes", "mensajes:index", "Mensajes", "mensaje", c("mensajes")),
            ("cuenta", "cuentas:cuenta", "Mi cuenta", "cuenta", 0),
        ]
    elif usuario.rol == "admin":
        filas = [
            ("inicio", "nucleo:inicio", "Inicio", "inicio", 0),
            ("usuarios", "cuentas:admin_personas", "Personas", "usuarios", 0),
            ("admin-cursos", "academico:admin_cursos", "Cursos", "cursos", 0),
            ("ajustes", "nucleo:ajustes", "Ajustes", "ajustes", 0),
            ("cuenta", "cuentas:cuenta", "Mi cuenta", "cuenta", 0),
        ]
    else:  # dirección
        filas = [
            ("inicio", "nucleo:inicio", "Inicio", "inicio", 0),
            ("cursos", "academico:modulos", "Módulos", "cursos", 0),
            ("cuenta", "cuentas:cuenta", "Mi cuenta", "cuenta", 0),
        ]
    return [(clave, url_o_numeral(nombre), texto, ico, num) for clave, nombre, texto, ico, num in filas]
