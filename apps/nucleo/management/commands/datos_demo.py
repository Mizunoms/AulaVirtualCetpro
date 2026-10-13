"""Crea cuentas de demostración para probar el aula en tu PC (solo con DEBUG=True).

    .venv\\Scripts\\python manage.py datos_demo

Cuentas (la contraseña de todas está en CLAVE_DEMO, abajo):
    Administrador   demo.admin@cetpro.com   → en «Soy profesor» escribe: demo.admin
    Docente         demo.docente@cetpro.com → en «Soy profesor» escribe: demo.docente
    Alumno          DNI 11111111            → en «Soy alumno»

Nunca se usa en el servidor real: el comando se niega a correr si DEBUG es False.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.cuentas.models import Rol, Usuario

CLAVE_DEMO = "demo-1234"

CUENTAS = [
    {"correo": "demo.admin@cetpro.com", "nombres": "Demo", "apellidos": "Administrador", "rol": Rol.ADMIN, "is_staff": True},
    {"correo": "demo.docente@cetpro.com", "nombres": "Demo", "apellidos": "Docente", "rol": Rol.DOCENTE},
    {"dni": "11111111", "nombres": "Demo", "apellidos": "Alumno", "rol": Rol.ALUMNO},
]


class Command(BaseCommand):
    help = "Crea (o repone) las cuentas de demostración. Solo con DEBUG=True."

    def handle(self, *args, **opciones):
        if not settings.DEBUG:
            raise CommandError("Las cuentas de demostración solo se crean en tu PC (DEBUG=True).")
        for datos in CUENTAS:
            clave = {"correo": datos["correo"]} if "correo" in datos else {"dni": datos["dni"]}
            usuario, creado = Usuario.objects.update_or_create(
                **clave, defaults={k: v for k, v in datos.items() if k not in clave}
            )
            usuario.set_password(CLAVE_DEMO)
            usuario.save()
            self.stdout.write(f"{'Creada' if creado else 'Repuesta'}: {usuario.rol} · {usuario.identificador}")
        self.stdout.write("Contraseña de las tres: la de CLAVE_DEMO en apps/nucleo/management/commands/datos_demo.py")
