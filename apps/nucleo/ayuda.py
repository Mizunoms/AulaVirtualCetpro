"""Contenido de la ayuda: el tutorial de primera vez (un paso a la vez) y el resumen del sistema (pantalla «Ayuda»).

Todo sale de aquí, así el recorrido y la pantalla de ayuda dicen siempre lo mismo. Textos en español simple, frases cortas.
Los íconos son los de `iconos.py`. Si cambia el nombre de un botón del aula, hay que cambiarlo también aquí.
"""

from dataclasses import dataclass

from apps.cuentas.models import Rol


@dataclass(frozen=True)
class Paso:
    icono: str
    titulo: str
    texto: str


_VER_Y_ESCUCHAR = Paso(
    "letra",
    "Para ver y escuchar mejor",
    "En «Mi cuenta» puedes poner la letra más grande, usar colores de alto contraste o el modo oscuro, "
    "y activar «Leer en voz alta» para que te lean los textos.",
)
_DUDAS = Paso(
    "ayuda",
    "Si te queda una duda",
    "Toca «Ayuda» cuando quieras: está en «Mi cuenta» y al final del Inicio. Allí puedes repetir este recorrido.",
)

PASOS = {
    Rol.ALUMNO: [
        Paso(
            "inicio",
            "Bienvenido al aula virtual",
            "Aquí está todo lo de tu curso: tus clases, tus tareas y tus notas. La puedes usar desde el celular o desde "
            "la computadora. Este recorrido dura un minuto.",
        ),
        Paso(
            "inicio",
            "Inicio",
            "Es lo primero que ves. Te muestra lo que tienes pendiente y lo que vence pronto. Toca el botón azul de una tarea para empezar.",
        ),
        Paso(
            "cursos",
            "Mis módulos",
            "Aquí están tus cursos. Entra a uno para ver sus clases, los materiales (fotos, PDF y videos) y las tareas.",
        ),
        Paso(
            "camara",
            "Entregar una tarea con foto",
            "Abre la tarea y toca «Tomar foto». Luego toca «Confirmar y enviar tarea». "
            "Si te equivocas, puedes enviarla otra vez hasta que tenga nota.",
        ),
        Paso(
            "examen",
            "Exámenes y formularios",
            "Son preguntas que respondes en el aula. Cuando tocas «Empezar», corre el reloj. Al final toca «Enviar».",
        ),
        Paso("notas", "Mis notas", "Aquí ves tus notas, tu asistencia y si vas aprobando."),
        Paso("mensaje", "Mensajes", "Escríbele a tu profesor si tienes una duda. También puedes mandarle una foto."),
        Paso("campana", "Avisos", "La campana de arriba te avisa cuando hay una tarea nueva o cuando te ponen una nota."),
        _VER_Y_ESCUCHAR,
        _DUDAS,
    ],
    Rol.DOCENTE: [
        Paso(
            "inicio",
            "Bienvenido al aula virtual",
            "Aquí organizas tus módulos: publicas materiales y tareas, tomas la asistencia y calificas. "
            "Este recorrido dura un minuto.",
        ),
        Paso(
            "cursos",
            "Mis módulos",
            "Entra a un módulo para ver sus clases, sus alumnos y sus tareas. Cada módulo tiene un código: "
            "dáselo a tus alumnos para que creen su cuenta.",
        ),
        Paso(
            "carpeta",
            "Clases",
            "Cada módulo se organiza en clases. Dentro de una clase subes materiales, dejas tareas y creas exámenes.",
        ),
        Paso(
            "tarea",
            "Dejar una tarea",
            "Toca «Crear tarea». Escribe el nombre, qué deben hacer y hasta cuándo. "
            "Tus alumnos la entregan con una foto desde su celular.",
        ),
        Paso(
            "examen",
            "Exámenes y formularios",
            "Crea preguntas como en un formulario de Google. En un examen la nota se calcula sola. En un trabajo, tú pones la nota.",
        ),
        Paso(
            "calificar",
            "Por calificar",
            "Aquí aparecen las entregas de tus alumnos. Abre una, mira la foto, pon la nota y escribe un comentario.",
        ),
        Paso("calendario", "Asistencia y notas", "En cada módulo puedes tomar la asistencia del día y ver el registro de notas."),
        Paso(
            "mensaje",
            "Mensajes y avisos",
            "Escribe a un alumno o a todo el módulo. También puedes publicar un aviso que todos ven al entrar.",
        ),
        _VER_Y_ESCUCHAR,
        _DUDAS,
    ],
    Rol.ADMIN: [
        Paso(
            "inicio",
            "Bienvenido al aula virtual",
            "Desde aquí administras el aula del CETPRO: las personas, los módulos y los ajustes. Este recorrido dura un minuto.",
        ),
        Paso(
            "usuarios",
            "Personas",
            "Crea docentes y alumnos, carga listas de alumnos y de docentes desde Excel, da contraseñas nuevas y desactiva cuentas.",
        ),
        Paso(
            "cursos",
            "Cursos y módulos",
            "Crea los módulos a mano o cargando el Excel del plan de estudios. "
            "Cada módulo tiene su docente, su turno y sus alumnos.",
        ),
        Paso(
            "ajustes",
            "Ajustes",
            "Cambia el nombre, el logo y los colores del aula, el WhatsApp de ayuda y la lista de cursos.",
        ),
        Paso(
            "alerta",
            "Registro de actividad",
            "Muestra quién entró y qué cambió. Lo ves desde el Inicio, en «Ver todo el registro».",
        ),
        _VER_Y_ESCUCHAR,
        _DUDAS,
    ],
    Rol.DIRECCION: [
        Paso(
            "inicio",
            "Bienvenido al aula virtual",
            "Aquí ves cómo van los módulos del CETPRO. Este recorrido dura un minuto.",
        ),
        Paso(
            "cursos",
            "Módulos",
            "Entra a un módulo para ver sus clases, tareas, notas y asistencia.",
        ),
        _VER_Y_ESCUCHAR,
        _DUDAS,
    ],
}

# Qué es el aula (igual para todos) y qué puede hacer cada persona
QUE_ES = (
    "El Aula Virtual del CETPRO es el lugar donde los docentes publican materiales y tareas, y los alumnos entregan "
    "sus trabajos con una foto y ven sus notas. Funciona en el celular y en la computadora."
)

PUEDES = {
    Rol.ALUMNO: "Como alumno puedes ver tus clases y materiales, entregar tareas con foto, responder exámenes, "
    "ver tus notas y tu asistencia, y escribirle a tu profesor.",
    Rol.DOCENTE: "Como docente puedes organizar tus módulos en clases, subir materiales, dejar tareas con foto, "
    "crear exámenes, calificar, tomar la asistencia y escribirle a tus alumnos.",
    Rol.ADMIN: "Como administrador puedes crear y cuidar las cuentas, armar los cursos y módulos, y cambiar los ajustes del aula.",
    Rol.DIRECCION: "Como dirección puedes ver cómo van los módulos: sus clases, tareas, notas y asistencia.",
}

PREGUNTAS = {
    Rol.ALUMNO: [
        (
            "No puedo entrar",
            "Revisa que escribiste bien tu DNI (8 números). Si es tu primera vez, toca «¿Es tu primera vez? Crea tu contraseña "
            "aquí». Si olvidaste tu contraseña, pídele una nueva a tu profesor.",
        ),
        (
            "Me equivoqué de foto",
            "Abre la tarea y toca «¿Te equivocaste? Envíala otra vez». Puedes hacerlo hasta que el profesor ponga la nota.",
        ),
        (
            "Entregué tarde, ¿qué pasa?",
            "Depende de cada tarea. En «Cómo te van a calificar» dice si se acepta tarde y cuántos puntos se restan.",
        ),
        (
            "Me piden crear una contraseña nueva",
            "La que te dieron es temporal. Toca «Crear mi nueva contraseña» y elige una que recuerdes. Si no puedes ahora, toca "
            "«Más tarde»: sigues dentro del aula y arriba te queda el botón para hacerlo después.",
        ),
        ("¿Dónde veo mi nota?", "En «Mis notas». Además te llega un aviso en la campana."),
        ("La letra se ve muy chica", "En «Mi cuenta» elige la letra «Grande» o «Muy grande»."),
    ],
    Rol.DOCENTE: [
        (
            "¿Cómo invito a mis alumnos?",
            "En tu módulo está el código de inscripción. Envíalo por WhatsApp: cada alumno toca «Crea tu contraseña aquí» y lo "
            "escribe con su DNI. También puedes cargar una lista de alumnos.",
        ),
        (
            "Un alumno olvidó su contraseña",
            "Entra a la lista de alumnos del módulo y toca «Nueva contraseña» junto a su nombre. Dásela por WhatsApp.",
        ),
        (
            "Me piden crear una contraseña nueva",
            "La que te dieron es temporal. Toca «Crear mi nueva contraseña» y elige una que recuerdes. Si no puedes ahora, toca "
            "«Más tarde»: sigues dentro del aula y arriba te queda el botón para hacerlo después.",
        ),
        ("¿Cómo califico?", "Entra a «Por calificar», abre una entrega, escribe la nota y guarda."),
        (
            "Me equivoqué al crear una tarea o un formulario",
            "Puedes cambiarlo. Si lo borras, va a la papelera del módulo y lo recuperas durante 30 días.",
        ),
    ],
    Rol.ADMIN: [
        (
            "Tengo una lista en Excel. ¿Cómo la cargo?",
            "En «Personas» toca «Cargar lista de alumnos» o «Cargar lista de docentes». Sube el Excel o pega la lista; en cada "
            "pantalla puedes descargar un modelo para llenar. Las contraseñas temporales se muestran una sola vez.",
        ),
        (
            "¿Cómo creo una cuenta?",
            "En «Personas» toca «Nuevo docente» o «Nuevo alumno». El aula te muestra la contraseña temporal una sola vez: "
            "cópiala o mándala por WhatsApp.",
        ),
        (
            "Una persona olvidó su contraseña",
            "En «Personas», busca a la persona, toca «Más» y luego «Resetear contraseña».",
        ),
        (
            "¿Eliminar o desactivar?",
            "«Eliminar» borra de verdad y pide confirmación. «Desactivar» solo esconde la cuenta, sin borrar nada.",
        ),
    ],
    Rol.DIRECCION: [],
}


def pasos_de(rol):
    """Los pasos del tutorial para ese rol (si el rol no se conoce, los del alumno)."""
    return PASOS.get(rol, PASOS[Rol.ALUMNO])


def resumen_de(rol):
    """Todo lo que muestra la pantalla de ayuda para ese rol."""
    rol = rol if rol in PASOS else Rol.ALUMNO
    return {
        "que_es": QUE_ES,
        "puedes": PUEDES[rol],
        "pasos": pasos_de(rol),
        "preguntas": PREGUNTAS[rol],
    }
