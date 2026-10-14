"""Pasa los datos del sistema anterior (PHP + MariaDB) a este sistema (Django + PostgreSQL).

Primero un ensayo (no guarda nada):
    python manage.py migrar_desde_php --base aula_virtual --archivos C:\\ruta\\src\\storage\\uploads --solo-revisar
Después, el pase de verdad (en una base nueva, sin personas):
    python manage.py migrar_desde_php --base aula_virtual --archivos C:\\ruta\\src\\storage\\uploads

La contraseña de la base anterior se lee de la variable de entorno ORIGEN_CLAVE (o se pide con --pedir-clave): así no queda
escrita en el historial de la terminal. La base anterior solo se lee; nunca se modifica."""

import os
from getpass import getpass

from django.core.management.base import BaseCommand, CommandError

from apps.nucleo.migracion_php import MigracionError, Migrador, OrigenMySQL


class Command(BaseCommand):
    help = "Pasa los datos del sistema anterior (PHP + MariaDB) a este sistema. Usa --solo-revisar para ensayar."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1", help="Servidor de la base anterior (por defecto 127.0.0.1).")
        parser.add_argument("--puerto", type=int, default=3306, help="Puerto de la base anterior (por defecto 3306).")
        parser.add_argument("--usuario", default="root", help="Usuario de la base anterior (por defecto root).")
        parser.add_argument("--base", default="aula_virtual", help="Nombre de la base anterior (por defecto aula_virtual).")
        parser.add_argument("--pedir-clave", action="store_true", help="Pide la contraseña de la base anterior en la terminal.")
        parser.add_argument(
            "--archivos",
            default="",
            help="Carpeta de archivos subidos del sistema anterior (src/storage/uploads). Sin ella no se copian.",
        )
        parser.add_argument("--solo-revisar", action="store_true", help="Ensayo: hace todo, cuenta y deshace; no guarda nada.")
        parser.add_argument(
            "--desactivar-claves-desconocidas",
            action="store_true",
            help="Pasa desactivadas las cuentas cuya contraseña no es bcrypt (por defecto, la migración se detiene y las lista).",
        )
        parser.add_argument(
            "--con-cuentas-de-prueba",
            action="store_true",
            help="Pasa también las cuentas del antiguo «modo prueba» (quedan desactivadas).",
        )

    def handle(self, *args, **opciones):
        clave = getpass("Contraseña de la base anterior: ") if opciones["pedir_clave"] else os.environ.get("ORIGEN_CLAVE", "")
        try:
            origen = OrigenMySQL(opciones["host"], opciones["puerto"], opciones["usuario"], clave, opciones["base"])
            try:
                informe = Migrador(
                    origen,
                    carpeta_archivos=opciones["archivos"] or None,
                    con_cuentas_de_prueba=opciones["con_cuentas_de_prueba"],
                    desactivar_claves_desconocidas=opciones["desactivar_claves_desconocidas"],
                    solo_revisar=opciones["solo_revisar"],
                ).correr()
            finally:
                origen.cerrar()
        except MigracionError as e:
            raise CommandError(str(e)) from e
        self.stdout.write(informe.texto())
        if opciones["solo_revisar"]:
            self.stdout.write(
                self.style.WARNING("\nEra un ensayo. Para pasar los datos de verdad, vuelve a correr sin --solo-revisar.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("\nListo. Entra con una cuenta del sistema anterior para comprobar."))
