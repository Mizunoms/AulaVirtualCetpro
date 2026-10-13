"""Carga los mismos datos de prueba que usaba el sistema anterior (database/datos_prueba.sql del repositorio PHP), para correr
sus pruebas HTTP contra este sistema (carpeta `aceptacion/`).

Cuentas: administrador y dirección con «CetproAdmin2026»; docentes (20000001 a 20000008) y alumnos (30000001 a 30000006) con su DNI
como contraseña. Los números de id salen en el mismo orden que antes (usuarios 1 a 16, módulos 1 a 8).

SOLO para la base de pruebas de aceptación: se niega a correr en otra."""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.academico.models import Aviso, Clase, Modulo
from apps.cuentas.models import Rol, Usuario
from apps.formularios.models import Formulario, Pregunta
from apps.tareas.models import PoliticaTardia, Tarea

CLAVE_ADMIN = "CetproAdmin2026"

USUARIOS = [
    ("10000001", "admin@cetpro.test", "Administrador", "del Aula", Rol.ADMIN, CLAVE_ADMIN),
    ("10000002", "direccion@cetpro.test", "Dirección", "CETPRO", Rol.DIRECCION, CLAVE_ADMIN),
    ("20000001", "rosa.paredes@cetpro.test", "Rosa Elena", "Paredes Huamán", Rol.DOCENTE, None),
    ("20000002", "jorge.salazar@cetpro.test", "Jorge Luis", "Salazar Ríos", Rol.DOCENTE, None),
    ("20000003", "carmen.villanueva@cetpro.test", "Carmen Rosa", "Villanueva Torres", Rol.DOCENTE, None),
    ("20000004", "luis.quispe@cetpro.test", "Luis Alberto", "Quispe Mendoza", Rol.DOCENTE, None),
    ("20000005", "gladys.flores@cetpro.test", "Gladys Mercedes", "Flores Cárdenas", Rol.DOCENTE, None),
    ("20000006", "pedro.huaranga@cetpro.test", "Pedro Pablo", "Huaranga Soto", Rol.DOCENTE, None),
    ("20000007", "milagros.castillo@cetpro.test", "Milagros Yanet", "Castillo León", Rol.DOCENTE, None),
    ("20000008", "victor.ramos@cetpro.test", "Víctor Hugo", "Ramos Chávez", Rol.DOCENTE, None),
    ("30000001", "ana.quispe@cetpro.test", "Ana María", "Quispe Rojas", Rol.ALUMNO, None),
    ("30000002", "luis.mamani@cetpro.test", "Luis Fernando", "Mamani Torres", Rol.ALUMNO, None),
    ("30000003", "rosa.huaman@cetpro.test", "Rosa Isabel", "Huamán Díaz", Rol.ALUMNO, None),
    ("30000004", "carlos.flores@cetpro.test", "Carlos Alberto", "Flores Vega", Rol.ALUMNO, None),
    ("30000005", "diana.chavez@cetpro.test", "Diana Carolina", "Chávez Ruiz", Rol.ALUMNO, None),
    ("30000006", "jorge.ramos@cetpro.test", "Jorge Enrique", "Ramos Paz", Rol.ALUMNO, None),
]

# (nombre del curso/especialidad, dni del docente, turno, horario)
MODULOS = [
    ("Peluquería y Barbería", "20000001", "mañana", "8:00 a. m. a 1:00 p. m."),
    ("Soporte Técnico", "20000002", "mañana", "8:00 a. m. a 1:00 p. m."),
    ("Panadería y Pastelería", "20000003", "mañana", "8:00 a. m. a 1:00 p. m."),
    ("Soldadura Universal", "20000004", "noche", "6:00 p. m. a 10:30 p. m."),
    ("Costura y Acabados", "20000005", "mañana", "8:00 a. m. a 1:00 p. m."),
    ("Técnicas de Cultivo Agrícolas", "20000006", "tarde", "1:30 p. m. a 6:00 p. m."),
    ("Artesanía y Manualidades", "20000007", "noche", "6:00 p. m. a 10:30 p. m."),
    ("Diseño de Piezas de Joyería", "20000008", "noche", "6:00 p. m. a 10:30 p. m."),
]


def _fin_del_dia(dias):
    d = timezone.localdate() + timedelta(days=dias)
    return timezone.make_aware(timezone.datetime(d.year, d.month, d.day, 23, 59))


class Command(BaseCommand):
    help = "Carga los datos de prueba del sistema anterior en la base de aceptación (nunca en la real)."

    def handle(self, *args, **opciones):
        nombre_base = settings.DATABASES["default"]["NAME"]
        if "aceptacion" not in str(nombre_base):
            raise CommandError(
                f"Este comando solo corre en una base de aceptación (su nombre lleva «aceptacion»). Esta es «{nombre_base}»."
            )
        if Usuario.objects.exists():
            raise CommandError("La base ya tiene personas. Usa una base nueva.")
        por_dni = {}
        for dni, correo, nombres, apellidos, rol, clave in USUARIOS:
            por_dni[dni] = Usuario.objects.create_user(
                correo=correo, password=clave or dni, rol=rol, nombres=nombres, apellidos=apellidos, dni=dni
            )
        modulos = []
        for esp, dni_docente, turno, horario in MODULOS:
            modulos.append(
                Modulo.crear(
                    nombre=f"{esp} – Módulo I", especialidad=esp, modulo="Módulo I", periodo="2026-II", turno=turno,
                    horario=horario, docente=por_dni[dni_docente],
                )
            )  # fmt: skip
        pelu, pan = modulos[0], modulos[2]
        for dni in ("30000001", "30000002", "30000003", "30000004", "30000005", "30000006"):
            pelu.matricular(por_dni[dni])
        for dni in ("30000001", "30000002"):
            pan.matricular(por_dni[dni])

        clase1 = Clase.crear(pelu, "Higiene y seguridad en el taller")
        clase2 = Clase.crear(pelu, "Corte básico")
        Tarea.objects.create(
            clase=clase1,
            titulo="Hoja de operaciones: herramientas del taller",
            instrucciones="Escribe en tu cuaderno las herramientas del taller y para qué sirve cada una. Toma una foto clara de la hoja.",
            fecha_limite=_fin_del_dia(-2),
            politica_tardia=PoliticaTardia.PENALIDAD,
            penalidad_puntos=2,
        )
        Tarea.objects.create(
            clase=clase2,
            titulo="Foto de corte básico",
            instrucciones="Toma una foto del corte terminado en tu modelo, de frente y de perfil.",
            fecha_limite=_fin_del_dia(3),
            politica_tardia=PoliticaTardia.PENALIDAD,
            penalidad_puntos=2,
        )
        Aviso.objects.create(
            modulo=pelu,
            autor=por_dni["20000001"],
            titulo="Bienvenidos al aula virtual",
            contenido="Bienvenidos al aula virtual. Aquí encontrarán las tareas, los materiales y sus notas. Mañana traer peine, tijera y capa.",
        )

        examen = Formulario.objects.create(
            clase=clase2,
            modo="examen",
            titulo="Examen: corte básico y bioseguridad",
            instrucciones="Lee cada pregunta con calma. Tienes 15 minutos y 2 intentos.",
            fecha_limite=_fin_del_dia(5),
            tiempo_minutos=15,
            intentos_max=2,
            mezclar=False,
            mostrar_respuestas=True,
            publicado=True,
        )

        def pregunta(tipo, enunciado, puntos, opciones=(), **extra):
            return Pregunta.guardar(
                examen,
                None,
                {
                    "tipo": tipo, "enunciado": enunciado, "obligatoria": True, "puntos": puntos,
                    "opciones": [(texto, correcta, "opcion") for texto, correcta in opciones], **extra,
                },
            )  # fmt: skip

        pregunta(
            "opcion",
            "¿Qué herramienta se usa para desenredar el cabello antes del corte?",
            2,
            [("Peine de dientes anchos", True), ("Navaja", False), ("Secadora", False), ("Tijera de entresacar", False)],
        )
        pregunta(
            "vf", "Se debe desinfectar la tijera después de atender a cada cliente.", 1, [("Verdadero", True), ("Falso", False)]
        )
        pregunta(
            "multiple",
            "¿Cuáles son elementos de bioseguridad en el taller? (marca todas las correctas)",
            3,
            [("Guantes", True), ("Mascarilla", True), ("Anillos y pulseras", False), ("Capa para el cliente", True)],
        )
        pregunta(
            "corta", "¿Cómo se llama el corte que pasa de corto a largo de forma gradual?", 2, aceptadas="degrafilado\ndegradado"
        )
        pregunta("abierta", "Explica con tus palabras cómo recibes a un cliente cuando llega al salón.", 2)
        self.stdout.write(self.style.SUCCESS("Datos de aceptación cargados (16 personas, 8 módulos, 2 tareas, 1 examen)."))
