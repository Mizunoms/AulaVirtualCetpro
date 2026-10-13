"""Qué se borra junto con una cuenta.

Cada parte del aula (trabajos, asistencia, tests, avisos, preguntas, mensajes…) registra aquí cómo contar lo suyo, para que la
pantalla «Eliminar cuentas» diga con palabras simples qué se pierde. Igual que `apps.academico.resumen`, pero para personas.
"""

# (orden en la frase, texto en singular, texto en plural, función(usuario) → cantidad)
CONTADORES = []


def registrar_contador(orden, uno, varios, funcion):
    CONTADORES.append((orden, uno, varios, funcion))


def resumen_al_eliminar(usuario):
    """Frases como «3 trabajos entregados», «1 mensaje»; lista vacía si la cuenta no tiene nada."""
    from apps.nucleo.utils import plural

    frases = []
    for _orden, uno, varios, funcion in sorted(CONTADORES, key=lambda c: c[0]):
        n = funcion(usuario)
        if n > 0:
            frases.append(plural(n, uno, varios))
    return frases
