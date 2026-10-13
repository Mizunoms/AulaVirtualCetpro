"""Borra los archivos subidos cuando se elimina de verdad lo que los tenía (una tarea, un trabajo, un mensaje…).

Uso en un modelo:

    @borra_archivos("archivo_ruta", "retro_ruta")
    class Entrega(models.Model): ...

Los archivos se borran recién cuando la base ya quedó bien (al confirmar la transacción), no antes.
"""

from django.db import transaction
from django.db.models.signals import post_delete

from . import archivos


def borra_archivos(*campos):
    def decorador(modelo):
        def al_borrar(sender, instance, **kwargs):
            rutas = [getattr(instance, c, "") for c in campos]
            transaction.on_commit(lambda: [archivos.borrar(r) for r in rutas if r])

        post_delete.connect(al_borrar, sender=modelo, weak=False, dispatch_uid=f"borrar_archivos_{modelo.__name__}")
        return modelo

    return decorador
