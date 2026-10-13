"""Lo que tiene cada clase (materiales, tareas, formularios) y lo que el alumno tiene pendiente.

Cada parte del aula que pone cosas dentro de las clases (materiales, tareas, formularios…) se registra aquí con una
función que devuelve `ItemClase`. Así la página del módulo, la clase y el inicio del alumno no necesitan conocer los
detalles de cada tipo de contenido.
"""

from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

# función(modulo, usuario, acceso) → list[ItemClase]. `acceso` es «docente», «alumno» o «lectura».
PROVEEDORES = []
# función(modulo) → cantidad de cosas por calificar (docente)
POR_CALIFICAR = []
# función(alumno) → list[ItemClase] pendientes de todos sus módulos (para el Inicio y «Mis módulos»)
PENDIENTES_DE_ALUMNO = []
# función(modulo) → {"tomada_hoy": bool, "registrados_hoy": int}
ASISTENCIA_HOY = []
# función(modulo, alumno) → {"promedio": nota o None, "asistencia": {"pct", "vino", "total"} o None}
RESUMEN_ALUMNO = []
# función(modulo) → {alumno_id: {"pct": int, "vino": int, "total": int}}
ASISTENCIA_POR_ALUMNO = []


@dataclass
class ItemClase:
    """Algo que está dentro de una clase y se muestra en una fila o tarjeta."""

    clase_id: int
    tipo: str  # «material», «tarea» o «examen»
    titulo: str
    url: str
    icono: str = ""  # nombre del ícono (si no hay `etiqueta`)
    etiqueta: str = ""  # texto corto en la cajita (PDF, Word…) en vez del ícono
    color: str = "ico-gris"  # ico-rojo, ico-azul, ico-ambar, ico-verde, ico-gris
    detalle: str = ""  # segunda línea
    accion: str = ""  # «Descargar», «Ver», «Abrir» (materiales)
    nueva_pestana: bool = False
    chip: str = ""
    chip_clase: str = "chip-gris"
    limite: datetime | None = None  # fecha de entrega o cierre
    hecha: bool = False  # el alumno ya la hizo
    cuenta_en_avance: bool = False  # cuenta para la barra de avance (tareas y tests con nota)
    abierta: bool = True  # se puede entregar o responder ahora
    clase_titulo: str = ""
    modulo_nombre: str = ""
    modulo_id: int = 0
    id: int = 0
    extra: dict = field(default_factory=dict)

    boton: str = ""  # texto del botón de la tarjeta («Subir foto o archivo», «Responder las preguntas»)
    resultado: str = ""  # lo que ve el alumno cuando ya la hizo («Ya la entregaste · Tu nota: 16»)

    @property
    def pendiente(self):
        """Falta hacerla y todavía se puede."""
        return self.tipo != "material" and not self.hecha and self.abierta

    @property
    def urgente(self):
        """Vence en menos de un día (o ya venció)."""
        return self.limite is not None and (self.limite - timezone.now()).total_seconds() < 86400

    @property
    def es_examen(self):
        return self.tipo == "examen"


def registrar_proveedor(funcion):
    PROVEEDORES.append(funcion)
    return funcion


def items_del_modulo(modulo, usuario, acceso):
    """Todo lo que hay en las clases del módulo (para quien lo ve)."""
    items = []
    for proveedor in PROVEEDORES:
        items.extend(proveedor(modulo, usuario, acceso))
    return items


def por_clase(items):
    """{clase_id: {"materiales": [...], "tareas": [...]}} y {clase_id: {"materiales": n, "tareas": n, "pendientes": n}}"""
    contenido, cuenta = {}, {}
    for it in items:
        c = contenido.setdefault(it.clase_id, {"materiales": [], "tareas": []})
        k = cuenta.setdefault(it.clase_id, {"materiales": 0, "tareas": 0, "pendientes": 0})
        if it.tipo == "material":
            c["materiales"].append(it)
            k["materiales"] += 1
        else:
            c["tareas"].append(it)
            k["tareas"] += 1
            if it.pendiente:
                k["pendientes"] += 1
    return contenido, cuenta


def avance_alumno(items):
    """Cuántas tareas y tests ya hizo el alumno (barra de avance): {"avance": % o None, "pendientes": n}"""
    cuentan = [it for it in items if it.cuenta_en_avance]
    hechas = sum(1 for it in cuentan if it.hecha)
    pendientes = sum(1 for it in items if it.pendiente)
    return {"avance": round(hechas * 100 / len(cuentan)) if cuentan else None, "pendientes": pendientes}


def por_calificar(modulo):
    return sum(f(modulo) for f in POR_CALIFICAR)


def asistencia_hoy(modulo):
    for f in ASISTENCIA_HOY:
        return f(modulo)
    return {"tomada_hoy": False, "registrados_hoy": 0}


def resumen_alumno(modulo, alumno, con_promedio=True):
    """Nota final y asistencia del alumno en el módulo (el promedio es más pesado de calcular: pedirlo solo si hace falta)."""
    for f in RESUMEN_ALUMNO:
        return f(modulo, alumno, con_promedio)
    return {"promedio": None, "asistencia": None}


# función(modulo) → (calificadas, pendientes de calificar) de tareas y tests del módulo
CALIFICACION_DEL_MODULO = []


def calificacion_del_modulo(modulo):
    calificadas = pendientes = 0
    for f in CALIFICACION_DEL_MODULO:
        c, p = f(modulo)
        calificadas += c
        pendientes += p
    return calificadas, pendientes


def asistencia_por_alumno(modulo):
    for f in ASISTENCIA_POR_ALUMNO:
        return f(modulo)
    return {}


# función(modulo) → list[dict] de las actividades con nota (tareas y exámenes): clave, id, titulo, fecha_limite,
# tipo_calificacion, tipo («tarea» o «examen»), modo, clase, etiqueta, url
ACTIVIDADES_CON_NOTA = []
# función(modulo) → {alumno_id: {clave: {"nota", "aprobado", "entrego", "comentario"}}}
ESTADOS_DE_ACTIVIDADES = []


def actividades_con_nota(modulo):
    actividades = [a for f in ACTIVIDADES_CON_NOTA for a in f(modulo)]
    actividades.sort(key=lambda a: a["fecha_limite"])
    return actividades


def estados_de_actividades(modulo):
    estados = {}
    for f in ESTADOS_DE_ACTIVIDADES:
        for alumno_id, claves in f(modulo).items():
            estados.setdefault(alumno_id, {}).update(claves)
    return estados


# función(modulo, usuario, acceso) → list[ItemClase] de los formularios del módulo (para «Tareas y exámenes»)
FORMULARIOS_DEL_MODULO = []
# función(docente) → list[dict] de lo que espera su revisión en «Por calificar» (tests y formularios)
BANDEJA_PENDIENTES = []
# función(alumno) → list[ItemClase] de los formularios que el alumno aún puede responder
FORMULARIOS_PENDIENTES = []
# función(alumno) → list[dict(titulo, modulo_nombre, nota_texto)] de las notas recientes
NOTAS_NUEVAS = []
# función(docente) → list[ItemClase] próximas fechas de sus tareas y tests (con extra["entregaron"], extra["texto_entregas"])
PROXIMAS_DE_DOCENTE = []
# función(docente) → list[(url, modulo_id)] de cada trabajo o test esperando nota
ESPERANDO_NOTA = []


def formularios_del_modulo(modulo, usuario, acceso):
    return [it for f in FORMULARIOS_DEL_MODULO for it in f(modulo, usuario, acceso)]


def bandeja_pendientes(docente):
    return [x for f in BANDEJA_PENDIENTES for x in f(docente)]


def notas_nuevas(alumno):
    return [n for f in NOTAS_NUEVAS for n in f(alumno)]


def proximas_de_docente(docente, limite=8):
    items = [it for f in PROXIMAS_DE_DOCENTE for it in f(docente)]
    items.sort(key=lambda it: it.limite.timestamp() if it.limite else float("inf"))
    return items[:limite]


def esperando_nota(docente):
    """Lista de (url, modulo_id) de lo que espera su nota, en todos los módulos del docente."""
    return [x for f in ESPERANDO_NOTA for x in f(docente)]


BLOQUES = [
    ("vencida", "Vencidas", "alerta", "fecha-vencida"),
    ("hoy", "Vence hoy", "reloj", "fecha-hoy"),
    ("proxima", "Vence pronto", "calendario", "fecha-proxima"),
]


def bloques_de_pendientes(grupos):
    """Para el panel «Tareas pendientes»: [(clave, título, ícono, clase de fecha, lista), …]"""
    return [(c, t, i, f, grupos.get(c, [])) for c, t, i, f in BLOQUES]


def pendientes_agrupados(alumno):
    """Tareas y exámenes que el alumno aún no entregó, por fecha: (lista, {«vencida», «hoy», «proxima»})."""
    pendientes = []
    for f in PENDIENTES_DE_ALUMNO:
        pendientes.extend(f(alumno))
    pendientes.sort(key=lambda it: it.limite or timezone.now())
    ahora = timezone.now()
    grupos = {"vencida": [], "hoy": [], "proxima": []}
    for it in pendientes:
        if it.limite is None:
            clave = "proxima"
        elif it.limite < ahora:
            clave = "vencida"
        elif timezone.localtime(it.limite).date() == timezone.localdate():
            clave = "hoy"
        else:
            clave = "proxima"
        grupos[clave].append(it)
    return pendientes, grupos
