"""Respaldo de la base de datos (y, si se pide, de los archivos subidos).

    python manage.py respaldo             → solo la base (rápido; para todos los días)
    python manage.py respaldo --archivos  → la base y las fotos/archivos en un .zip (una vez por semana)

Guarda en la carpeta de respaldos (RESPALDOS_CARPETA, por defecto storage/respaldos) y deja los 14 más recientes de cada tipo.
En Windows Server se programa con el Programador de tareas (ver docs/03-servidor-windows.md)."""

from django.core.management.base import BaseCommand, CommandError

from apps.academico import papelera
from apps.nucleo.respaldo import CONSERVAR, RespaldoError, respaldar


class Command(BaseCommand):
    help = "Respalda la base de datos (y con --archivos, también los archivos subidos)."

    def add_arguments(self, parser):
        parser.add_argument("--archivos", action="store_true", help="Guarda también las fotos y archivos subidos en un .zip.")
        parser.add_argument("--carpeta", default="", help="Dónde guardar los respaldos (por defecto, RESPALDOS_CARPETA).")
        parser.add_argument(
            "--conservar", type=int, default=CONSERVAR, help=f"Cuántos respaldos de cada tipo dejar (por defecto {CONSERVAR})."
        )

    def handle(self, *args, **opciones):
        if opciones["conservar"] < 1:
            raise CommandError("--conservar debe ser 1 o más.")
        try:
            r = respaldar(opciones["archivos"], opciones["carpeta"] or None, opciones["conservar"])
        except RespaldoError as e:
            raise CommandError(str(e)) from e
        self.stdout.write(f"Base respaldada: {r['base']} ({round(r['base'].stat().st_size / 1024)} KB)")
        if r["archivos"]:
            ruta, cantidad = r["archivos"]
            self.stdout.write(f"Archivos respaldados: {ruta} ({cantidad} archivos)")
        if r["borrados"]:
            self.stdout.write(f"Respaldos viejos borrados: {r['borrados']}")
        # Lo que lleva más de 30 días en la papelera se borra de verdad (ya quedó en este respaldo).
        vaciados = papelera.vaciar_viejos()
        if vaciados:
            self.stdout.write(f"Papelera: {vaciados} elementos de más de 30 días borrados.")
