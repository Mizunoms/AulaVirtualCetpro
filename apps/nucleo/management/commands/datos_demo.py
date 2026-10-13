"""Crea cuentas y un módulo de demostración para probar el aula en tu PC (solo con DEBUG=True).

    .venv\\Scripts\\python manage.py datos_demo

Cuentas (la contraseña de todas está en CLAVE_DEMO, abajo):
    Administrador   demo.admin@cetpro.com   → en «Soy profesor» escribe: demo.admin
    Docente         demo.docente@cetpro.com → en «Soy profesor» escribe: demo.docente
    Alumno          DNI 11111111            → en «Soy alumno»

También crea el módulo «Soporte Técnico – Módulo 1» del docente, con tres clases, un aviso y al alumno matriculado.
Nunca se usa en el servidor real: el comando se niega a correr si DEBUG es False.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.academico.models import Aviso, Clase, Modulo, UnidadDidactica
from apps.cuentas.models import Rol, Usuario

CLAVE_DEMO = "demo-1234"

CUENTAS = [
    {"correo": "demo.admin@cetpro.com", "nombres": "Demo", "apellidos": "Administrador", "rol": Rol.ADMIN, "is_staff": True},
    {"correo": "demo.docente@cetpro.com", "nombres": "Demo", "apellidos": "Docente", "rol": Rol.DOCENTE},
    {"dni": "11111111", "nombres": "Demo", "apellidos": "Alumno", "rol": Rol.ALUMNO, "telefono": "987654321"},
]

NOMBRE_MODULO = "Soporte Técnico – Módulo 1 (demo)"


class Command(BaseCommand):
    help = "Crea (o repone) las cuentas y el módulo de demostración. Solo con DEBUG=True."

    def handle(self, *args, **opciones):
        if not settings.DEBUG:
            raise CommandError("Las cuentas de demostración solo se crean en tu PC (DEBUG=True).")
        usuarios = {}
        for datos in CUENTAS:
            clave = {"correo": datos["correo"]} if "correo" in datos else {"dni": datos["dni"]}
            usuario, creado = Usuario.objects.update_or_create(
                **clave, defaults={k: v for k, v in datos.items() if k not in clave}
            )
            usuario.set_password(CLAVE_DEMO)
            usuario.save()
            usuarios[usuario.rol] = usuario
            self.stdout.write(f"{'Creada' if creado else 'Repuesta'}: {usuario.rol} · {usuario.identificador}")
        self._modulo(usuarios[Rol.DOCENTE], usuarios[Rol.ALUMNO])
        self.stdout.write("Contraseña de las tres: la de CLAVE_DEMO en apps/nucleo/management/commands/datos_demo.py")

    def _modulo(self, docente, alumno):
        modulo = Modulo.objects.filter(nombre=NOMBRE_MODULO).first()
        if modulo is None:
            modulo = Modulo.crear(
                nombre=NOMBRE_MODULO,
                especialidad="Soporte Técnico",
                modulo="Módulo 1",
                periodo="2026-II",
                turno="noche",
                horario="Lunes a viernes · 6:30 a 10:30 p. m.",
                docente=docente,
            )
            UnidadDidactica.guardar_lista(
                modulo,
                [
                    {"nombre": "Organización del área de trabajo", "creditos": 2, "horas": 48},
                    {"nombre": "Mantenimiento de equipos de cómputo", "creditos": 4, "horas": 96},
                ],
            )
            hoy = timezone.localdate()
            Clase.crear(
                modulo,
                "Seguridad y orden en el taller",
                hoy - timedelta(days=14),
                hoy - timedelta(days=8),
                "Aprenderás las normas básicas.",
            )
            Clase.crear(
                modulo,
                "Armado de una computadora",
                hoy - timedelta(days=7),
                hoy + timedelta(days=6),
                "Aprenderás a armar una PC paso a paso.",
            )
            Clase.crear(modulo, "Instalación de sistemas operativos", hoy + timedelta(days=7), hoy + timedelta(days=13))
            Aviso.crear(modulo, docente, "Mañana traer destornillador y pulsera antiestática.")
        modulo.matricular(alumno)
        self.stdout.write(f"Módulo: {modulo.nombre} · código {modulo.codigo_fmt}")
