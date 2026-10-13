"""Lo que el docente borra (tareas, formularios y materiales) queda 30 días en la papelera y se puede recuperar.
Después se borra de verdad, con sus archivos.

Cada tipo de contenido se registra con `registrar(...)`; su modelo debe tener `clase`, `titulo` y `eliminado`,
y un administrador `todos` que incluya lo borrado.
"""

from datetime import timedelta

from django.utils import timezone

DIAS = 30
TIPOS = {}  # clave → (nombre para mostrar, ícono, color, modelo)


def registrar(clave, nombre, icono, color, modelo):
    TIPOS[clave] = (nombre, icono, color, modelo)


def de_modulo(modulo):
    """Lo borrado de un módulo, lo más reciente primero."""
    ahora = timezone.now()
    filas = []
    for clave, (nombre, icono, color, modelo) in TIPOS.items():
        for x in modelo.todos.filter(clase__modulo=modulo, eliminado__isnull=False).select_related("clase"):
            quedan = DIAS - (ahora - x.eliminado).days
            filas.append(
                {
                    "id": x.pk,
                    "titulo": x.titulo,
                    "eliminado": x.eliminado,
                    "clase_titulo": x.clase.titulo,
                    "tipo": clave,
                    "tipo_nombre": nombre,
                    "icono": icono,
                    "color": color,
                    "quedan": max(1, quedan),
                }  # fmt: skip
            )
    filas.sort(key=lambda f: f["eliminado"], reverse=True)
    return filas


def recuperar(modulo, tipo, id):
    """Recupera algo de la papelera de ese módulo. Devuelve la clase donde volvió (o None si no existe)."""
    if tipo not in TIPOS:
        return None
    modelo = TIPOS[tipo][3]
    x = modelo.todos.filter(pk=id, clase__modulo=modulo, eliminado__isnull=False).first()
    if x is None:
        return None
    x.eliminado = None
    x.save(update_fields=["eliminado"])
    return x.clase_id


def vaciar_viejos():
    """Borra de verdad lo que lleva más de 30 días en la papelera (y sus archivos). Devuelve cuántos."""
    limite = timezone.now() - timedelta(days=DIAS)
    total = 0
    for _nombre, _icono, _color, modelo in TIPOS.values():
        for x in modelo.todos.filter(eliminado__lt=limite):
            x.delete()
            total += 1
    return total
