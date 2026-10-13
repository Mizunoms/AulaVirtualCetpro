"""Qué se pierde al eliminar un módulo.

Cada parte del aula (clases, tareas, formularios, mensajes…) registra aquí cómo contar lo suyo, para que la
pantalla «Eliminar módulo» pueda decir con palabras simples qué se borra, y para saber si ya hay trabajos de alumnos.
"""

# (texto en singular, texto en plural, función(modulo) → cantidad)
CONTADORES = []
# función(modulo) → True si ya hay trabajos, tests o asistencia de alumnos
REGISTROS_DE_ALUMNOS = []


def registrar_contador(uno, varios, funcion):
    CONTADORES.append((uno, varios, funcion))


def registrar_registros_de_alumnos(funcion):
    REGISTROS_DE_ALUMNOS.append(funcion)


def resumen_al_eliminar(modulo):
    """Frases como «2 clases», «14 trabajos entregados»; lista vacía si el módulo no tiene nada."""
    from apps.nucleo.utils import plural

    frases = []
    for uno, varios, funcion in CONTADORES:
        n = funcion(modulo)
        if n > 0:
            frases.append(plural(n, uno, varios))
    return frases


def tiene_registros_de_alumnos(modulo):
    """¿Ya hay trabajos, tests o asistencia de alumnos? Si es así, solo el administrador puede eliminar el módulo."""
    return any(funcion(modulo) for funcion in REGISTROS_DE_ALUMNOS)
