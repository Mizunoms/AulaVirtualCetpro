"""Formularios que el docente arma en el aula (como Google Forms): el alumno los responde y se corrigen.

Modo examen: preguntas con puntos y nota automática. Trabajo: el docente lee y pone la nota. Encuesta: sin nota.
Lo que el docente borra va a la papelera 30 días (`eliminado`): `objects` solo muestra lo que no está borrado; `todos` muestra todo.
"""

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.academico.models import Clase
from apps.nucleo import archivos
from apps.nucleo.archivos_borrado import borra_archivos
from apps.tareas.models import ActivosManager

# tipo → (nombre para el docente, indicación para el alumno)
TIPOS = {
    "opcion": ("Varias opciones (elige una)", "Elige una opción."),
    "multiple": ("Casillas (elige varias)", "Marca todas las que correspondan."),
    "desplegable": ("Lista desplegable", "Elige una opción de la lista."),
    "vf": ("Verdadero o falso", "Elige verdadero o falso."),
    "corta": ("Respuesta corta", "Escribe una palabra o frase corta."),
    "abierta": ("Párrafo (respuesta larga)", "Escribe tu respuesta con tus palabras."),
    "escala": ("Escala lineal (del 1 al 5…)", "Elige un número."),
    "fecha": ("Fecha", "Elige una fecha."),
    "hora": ("Hora", "Elige una hora."),
    "archivo": ("Subir archivo o foto", "Sube una foto o un archivo."),
    "cuadricula": ("Cuadrícula de opciones (una por fila)", "Elige una opción en cada fila."),
    "cuadricula_casillas": ("Cuadrícula de casillas (varias por fila)", "Marca las que correspondan en cada fila."),
    "seccion": ("Título y descripción (separa partes)", ""),
}
# El tipo de pregunta que el sistema puede corregir solo (en modo examen)
AUTOMATICOS = ("opcion", "multiple", "desplegable", "vf", "corta")
# Tipos con alternativas que escribe el docente
CON_OPCIONES = ("opcion", "multiple", "desplegable")
# Tipos que se contestan eligiendo alternativas
ELEGIR = ("opcion", "multiple", "desplegable", "vf")
CUADRICULAS = ("cuadricula", "cuadricula_casillas")
# Cómo se agrupan los tipos al elegirlos en el editor
GRUPOS_DE_TIPOS = [
    ("Elegir", ["opcion", "multiple", "desplegable", "vf"]),
    ("Escribir", ["corta", "abierta"]),
    ("Otros", ["escala", "fecha", "hora", "archivo"]),
    ("Cuadrículas", ["cuadricula", "cuadricula_casillas"]),
    ("Ordenar el formulario", ["seccion"]),
]

MODOS = {
    "examen": ("Examen", "Con puntos: la nota se calcula sola."),
    "trabajo": ("Trabajo", "Tú revisas las respuestas y pones la nota."),
    "encuesta": ("Encuesta", "Sin nota: solo para conocer opiniones o datos."),
}

TOLERANCIA_MIN = 2  # minutos de tolerancia después del tiempo límite (por demoras de conexión)
DIAS_PAPELERA = 30


class Formulario(models.Model):
    clase = models.ForeignKey(Clase, on_delete=models.CASCADE, related_name="formularios")
    modo = models.CharField(max_length=10, choices=[(k, v[0]) for k, v in MODOS.items()], default="examen")
    titulo = models.CharField(max_length=150)
    instrucciones = models.TextField(blank=True, default="")
    mensaje_final = models.CharField(max_length=500, blank=True, default="")  # lo que ve el alumno al enviar
    fecha_inicio = models.DateTimeField(null=True, blank=True)  # desde cuándo se puede responder (None = desde que se publica)
    fecha_limite = models.DateTimeField()
    tiempo_minutos = models.PositiveSmallIntegerField(null=True, blank=True)  # None = sin límite de tiempo
    intentos_max = models.PositiveSmallIntegerField(default=1)
    mezclar = models.BooleanField(default=False)  # cambia el orden de preguntas y alternativas
    mostrar_respuestas = models.BooleanField(default=True)  # al terminar, el alumno ve qué respondió bien
    publicado = models.BooleanField(default=False)
    creado = models.DateTimeField(default=timezone.now)
    eliminado = models.DateTimeField(null=True, blank=True)  # en la papelera

    objects = ActivosManager()
    todos = models.Manager()

    class Meta:
        verbose_name = "formulario"
        verbose_name_plural = "formularios"
        ordering = ["-fecha_limite", "id"]
        base_manager_name = "todos"

    def __str__(self):
        return self.titulo

    @property
    def modulo(self):
        return self.clase.modulo

    @property
    def nombre_modo(self):
        return MODOS[self.modo][0]

    @property
    def descripcion_modo(self):
        return MODOS[self.modo][1]

    @property
    def es_examen(self):
        return self.modo == "examen"

    @property
    def es_encuesta(self):
        return self.modo == "encuesta"

    @property
    def vencido(self):
        return self.fecha_limite < timezone.now()

    @property
    def abierto(self):
        """¿Se puede responder ahora? Publicado, con la clase visible y abierta, y dentro de las fechas."""
        ahora = timezone.now()
        return (
            self.publicado
            and self.clase.visible
            and self.clase.situacion == "abierta"
            and (self.fecha_inicio is None or self.fecha_inicio <= ahora)
            and self.fecha_limite > ahora
        )

    @property
    def de_clase_proxima(self):
        """¿La clase todavía no empieza? (el alumno no lo ve)"""
        return self.clase.situacion == "proxima"

    def hay_intentos(self):
        return self.intentos.exists()

    def preguntas_completas(self):
        """Las preguntas en el orden del docente, cada una con sus alternativas en `.opciones`, `.filas` y `.columnas`."""
        lista = list(self.preguntas.all())
        por_pregunta = {}
        for o in Opcion.objects.filter(pregunta__formulario=self).order_by("orden", "id"):
            por_pregunta.setdefault(o.pregunta_id, []).append(o)
        for p in lista:
            p.repartir(por_pregunta.get(p.pk, []))
        return lista

    @staticmethod
    def con_resumen(formularios):
        """Agrega a cada formulario `total_preguntas` y `total_puntos` (sin contar los títulos)."""
        formularios = list(formularios)
        ids = [f.pk for f in formularios]
        total = {
            f["formulario"]: f
            for f in Pregunta.objects.filter(formulario__in=ids)
            .exclude(tipo="seccion")
            .values("formulario")
            .annotate(n=models.Count("id"), pts=models.Sum("puntos"))
        }
        for f in formularios:
            fila = total.get(f.pk, {})
            f.total_preguntas = fila.get("n", 0)
            f.total_puntos = fila.get("pts") or 0
        return formularios

    def copiar_a(self, clase, mover):
        """Copia el formulario con sus preguntas (con imágenes propias) a otra clase. Las fechas se corren con `mover`."""
        nuevo = Formulario.objects.create(
            clase=clase,
            modo=self.modo,
            titulo=self.titulo,
            instrucciones=self.instrucciones,
            mensaje_final=self.mensaje_final,
            fecha_inicio=mover(self.fecha_inicio),
            fecha_limite=mover(self.fecha_limite),
            tiempo_minutos=self.tiempo_minutos,
            intentos_max=self.intentos_max,
            mezclar=self.mezclar,
            mostrar_respuestas=self.mostrar_respuestas,
            publicado=self.publicado,
        )
        for p in self.preguntas_completas():
            p.copiar_a(nuevo)
        return nuevo


@borra_archivos("imagen_ruta")
class Pregunta(models.Model):
    formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE, related_name="preguntas")
    tipo = models.CharField(max_length=20, choices=[(k, v[0]) for k, v in TIPOS.items()])
    enunciado = models.TextField()
    ayuda = models.CharField(max_length=500, blank=True, default="")  # descripción debajo de la pregunta
    imagen_ruta = models.CharField(max_length=255, blank=True, default="")  # foto opcional de la pregunta
    obligatoria = models.BooleanField(default=True)
    puntos = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    respuestas_aceptadas = models.TextField(blank=True, default="")  # «corta» en examen: una respuesta válida por línea
    explicacion = models.TextField(blank=True, default="")  # examen: se muestra al alumno al terminar
    permite_otra = models.BooleanField(default=False)  # alternativas: agrega «Otra» con texto libre
    escala_min = models.PositiveSmallIntegerField(null=True, blank=True)
    escala_max = models.PositiveSmallIntegerField(null=True, blank=True)
    etiqueta_min = models.CharField(max_length=60, blank=True, default="")
    etiqueta_max = models.CharField(max_length=60, blank=True, default="")
    orden = models.IntegerField(default=1)

    class Meta:
        verbose_name = "pregunta"
        verbose_name_plural = "preguntas"
        ordering = ["orden", "id"]

    def __str__(self):
        return self.enunciado[:60]

    @property
    def es_seccion(self):
        return self.tipo == "seccion"

    @property
    def nombre_tipo(self):
        return TIPOS[self.tipo][0]

    @property
    def indicacion(self):
        return self.ayuda or TIPOS[self.tipo][1]

    @property
    def es_automatica(self):
        return self.tipo in AUTOMATICOS

    def repartir(self, todas):
        """Reparte las alternativas en `opciones` y, para cuadrículas, en `filas` y `columnas`."""
        self.opciones, self.filas, self.columnas = [], [], []
        for o in todas:
            {"fila": self.filas, "columna": self.columnas}.get(o.grupo, self.opciones).append(o)

    def cargar_opciones(self):
        self.repartir(list(self.todas_las_opciones.order_by("orden", "id")))
        return self

    @property
    def respuestas_aceptadas_texto(self):
        return " · ".join(self.respuestas_aceptadas.splitlines())

    @classmethod
    def guardar(cls, formulario, pregunta, d):
        """Guarda una pregunta nueva (`pregunta` = None) o reemplaza la que hay (con sus alternativas).
        `d` lleva los datos de la pregunta y `d["opciones"]` = [(texto, correcta, grupo), …]."""
        with transaction.atomic():
            campos = {
                "tipo": d["tipo"],
                "enunciado": d["enunciado"],
                "ayuda": d.get("ayuda") or "",
                "imagen_ruta": d.get("imagen_ruta") or "",
                "obligatoria": bool(d["obligatoria"]),
                "puntos": d["puntos"],
                "respuestas_aceptadas": d.get("aceptadas") or "",
                "explicacion": d.get("explicacion") or "",
                "permite_otra": bool(d.get("permite_otra")),
                "escala_min": d.get("escala_min"),
                "escala_max": d.get("escala_max"),
                "etiqueta_min": d.get("etiqueta_min") or "",
                "etiqueta_max": d.get("etiqueta_max") or "",
            }
            if pregunta is None:
                orden = (cls.objects.filter(formulario=formulario).aggregate(m=models.Max("orden"))["m"] or 0) + 1
                pregunta = cls.objects.create(formulario=formulario, orden=orden, **campos)
            else:
                vieja = pregunta.imagen_ruta
                for k, v in campos.items():
                    setattr(pregunta, k, v)
                pregunta.save()
                pregunta.todas_las_opciones.all().delete()
                if vieja and vieja != pregunta.imagen_ruta:  # la imagen se quitó o se cambió: la vieja ya no hace falta
                    transaction.on_commit(lambda: archivos.borrar(vieja))
            Opcion.objects.bulk_create(
                [
                    Opcion(pregunta=pregunta, grupo=o[2] if len(o) > 2 else "opcion", texto=o[0], correcta=bool(o[1]), orden=i)
                    for i, o in enumerate(d["opciones"], start=1)
                ]
            )
        return pregunta

    def copiar_a(self, formulario, orden=None):
        """Copia la pregunta (con sus alternativas y su imagen propia) a un formulario."""
        self.cargar_opciones()
        nueva = Pregunta.guardar(
            formulario,
            None,
            {
                "tipo": self.tipo,
                "enunciado": self.enunciado,
                "ayuda": self.ayuda,
                "imagen_ruta": (archivos.copiar(self.imagen_ruta) or "") if self.imagen_ruta else "",
                "obligatoria": self.obligatoria,
                "puntos": self.puntos,
                "aceptadas": self.respuestas_aceptadas,
                "explicacion": self.explicacion,
                "permite_otra": self.permite_otra,
                "escala_min": self.escala_min,
                "escala_max": self.escala_max,
                "etiqueta_min": self.etiqueta_min,
                "etiqueta_max": self.etiqueta_max,
                "opciones": [(o.texto, o.correcta, o.grupo) for o in [*self.opciones, *self.filas, *self.columnas]],
            },
        )
        if orden is not None:
            Pregunta.objects.filter(pk=nueva.pk).update(orden=orden)
        return nueva

    @transaction.atomic
    def duplicar(self):
        """Copia la pregunta justo debajo de la original."""
        Pregunta.objects.filter(formulario=self.formulario, orden__gt=self.orden).update(orden=models.F("orden") + 1)
        return self.copiar_a(self.formulario, orden=self.orden + 1)

    @transaction.atomic
    def mover(self, subir):
        """Sube o baja la pregunta un lugar, cambiando su orden con la de al lado."""
        ids = list(Pregunta.objects.filter(formulario=self.formulario).order_by("orden", "id").values_list("pk", flat=True))
        i = ids.index(self.pk)
        j = i - 1 if subir else i + 1
        if j < 0 or j >= len(ids):
            return
        ids[i], ids[j] = ids[j], ids[i]
        for k, pk in enumerate(ids, start=1):
            Pregunta.objects.filter(pk=pk).update(orden=k)


class Opcion(models.Model):
    """Una alternativa de una pregunta; en las cuadrículas, una fila o una columna."""

    pregunta = models.ForeignKey(Pregunta, on_delete=models.CASCADE, related_name="todas_las_opciones")
    grupo = models.CharField(
        max_length=10, choices=[("opcion", "Opción"), ("fila", "Fila"), ("columna", "Columna")], default="opcion"
    )
    texto = models.CharField(max_length=500)
    correcta = models.BooleanField(default=False)
    orden = models.IntegerField(default=1)

    class Meta:
        verbose_name = "opción"
        verbose_name_plural = "opciones"
        ordering = ["orden", "id"]

    def __str__(self):
        return self.texto[:60]


class Intento(models.Model):
    """Lo que un alumno respondió en un formulario, y su corrección."""

    formulario = models.ForeignKey(Formulario, on_delete=models.CASCADE, related_name="intentos")
    alumno = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="intentos_de_formulario")
    inicio = models.DateTimeField(default=timezone.now)
    fin = models.DateTimeField(null=True, blank=True)  # None = todavía respondiendo
    fuera_tiempo = models.BooleanField(default=False)
    puntaje = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    puntaje_max = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    nota = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True
    )  # 0–20; None mientras falte revisar (o encuesta)
    revisado = models.BooleanField(default=False)
    comentario = models.TextField(blank=True, default="")  # comentario general del docente

    class Meta:
        verbose_name = "intento"
        verbose_name_plural = "intentos"
        ordering = ["id"]
        indexes = [models.Index(fields=["formulario", "alumno"], name="intento_form_alumno_idx")]

    def __str__(self):
        return f"{self.alumno} → {self.formulario}"

    @property
    def terminado(self):
        return self.fin is not None

    @property
    def fin_de_tiempo(self):
        """Hora en que se acaba el tiempo del intento (o la fecha límite si el formulario no tiene tiempo)."""
        f = self.formulario
        if f.tiempo_minutos:
            return min(self.inicio + timedelta(minutes=f.tiempo_minutos), f.fecha_limite)
        return f.fecha_limite

    @property
    def segundos_restantes(self):
        return int((self.fin_de_tiempo - timezone.now()).total_seconds())

    def respuestas_por_pregunta(self):
        """{pregunta_id: respuesta}"""
        return {r.pregunta_id: r for r in self.respuestas.all()}


@borra_archivos("archivo_ruta")
class Respuesta(models.Model):
    intento = models.ForeignKey(Intento, on_delete=models.CASCADE, related_name="respuestas")
    pregunta = models.ForeignKey(Pregunta, on_delete=models.CASCADE, related_name="respuestas")
    opciones = models.CharField(max_length=255, blank=True, default="")  # ids de las alternativas marcadas, separados por coma
    texto = models.TextField(blank=True, default="")  # texto, fecha, hora, número de escala, «Otra» o cuadrícula (JSON)
    archivo_ruta = models.CharField(max_length=255, blank=True, default="")  # pregunta de tipo archivo
    archivo_nombre = models.CharField(max_length=255, blank=True, default="")
    puntos = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)  # None = falta revisar
    comentario = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "respuesta"
        verbose_name_plural = "respuestas"
        constraints = [models.UniqueConstraint(fields=["intento", "pregunta"], name="respuesta_unica")]

    def __str__(self):
        return f"{self.intento} · {self.pregunta}"

    @property
    def ids_marcados(self):
        return [int(x) for x in self.opciones.split(",") if x.strip().isdigit()]

    @property
    def tiene_algo(self):
        return bool(self.opciones or self.texto or self.archivo_ruta)

    @property
    def es_imagen(self):
        return bool(self.archivo_ruta) and Path(self.archivo_ruta).suffix.lower().lstrip(".") in archivos.IMAGENES
