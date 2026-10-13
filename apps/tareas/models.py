"""Materiales de las clases, tareas con foto o archivo, entregas de los alumnos y su calificación.

Lo que el docente borra (materiales y tareas) va a la papelera 30 días (`eliminado`) y se puede recuperar:
`objects` solo muestra lo que no está borrado; `todos` muestra todo.
"""

import re
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.academico.models import Clase
from apps.nucleo.archivos_borrado import borra_archivos
from apps.nucleo.utils import nota_fmt


class ActivosManager(models.Manager):
    """Solo lo que no está en la papelera."""

    def get_queryset(self):
        return super().get_queryset().filter(eliminado__isnull=True)


class TipoMaterial(models.TextChoices):
    ARCHIVO = "archivo", "Archivo"
    ENLACE = "enlace", "Enlace"
    VIDEO = "video", "Video"


@borra_archivos("archivo_ruta")
class Material(models.Model):
    clase = models.ForeignKey(Clase, on_delete=models.CASCADE, related_name="materiales")
    titulo = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, default="")
    tipo = models.CharField(max_length=10, choices=TipoMaterial.choices)
    archivo_ruta = models.CharField(max_length=255, blank=True, default="")  # nombre aleatorio en storage/uploads
    archivo_nombre = models.CharField(max_length=255, blank=True, default="")  # nombre original
    url = models.CharField(max_length=500, blank=True, default="")
    creado = models.DateTimeField(default=timezone.now)
    eliminado = models.DateTimeField(null=True, blank=True)  # en la papelera (se recupera durante 30 días)

    objects = ActivosManager()
    todos = models.Manager()

    class Meta:
        verbose_name = "material"
        verbose_name_plural = "materiales"
        ordering = ["creado", "id"]
        base_manager_name = "todos"

    def __str__(self):
        return self.titulo

    @property
    def etiqueta(self):
        """«PDF», «Word», «Foto», «Video», «Enlace»…"""
        if self.tipo == TipoMaterial.VIDEO:
            return "Video"
        if self.tipo == TipoMaterial.ENLACE:
            return "Enlace"
        ext = Path(self.archivo_nombre).suffix.lower().lstrip(".")
        return {
            "pdf": "PDF", "doc": "Word", "docx": "Word", "ppt": "PPT", "pptx": "PPT", "xls": "Excel", "xlsx": "Excel",
            "jpg": "Foto", "jpeg": "Foto", "png": "Foto", "webp": "Foto", "heic": "Foto",
        }.get(ext, "Archivo")  # fmt: skip


class PoliticaTardia(models.TextChoices):
    NO_ACEPTA = "no_acepta", "No se acepta"
    ACEPTA = "acepta", "Se acepta"
    PENALIDAD = "penalidad", "Se acepta restando puntos"


class TipoCalificacion(models.TextChoices):
    NOTA = "nota", "Nota de 0 a 20"
    RUBRICA = "rubrica", "Rúbrica (nota de 0 a 20)"
    APROBADO = "aprobado", "Aprobó / No aprobó"


class TipoTarea(models.TextChoices):
    INDIVIDUAL = "individual", "Individual"
    GRUPAL = "grupal", "En grupo"


@borra_archivos("archivo_ruta")
class Tarea(models.Model):
    clase = models.ForeignKey(Clase, on_delete=models.CASCADE, related_name="tareas")
    titulo = models.CharField(max_length=150)
    instrucciones = models.TextField(blank=True, default="")
    criterios = models.TextField(blank=True, default="")  # lo que el docente revisará (uno por línea: «texto|puntos»)
    archivo_ruta = models.CharField(max_length=255, blank=True, default="")
    archivo_nombre = models.CharField(max_length=255, blank=True, default="")
    fecha_limite = models.DateTimeField()
    puntaje_max = models.DecimalField(max_digits=4, decimal_places=2, default=20)
    politica_tardia = models.CharField(max_length=10, choices=PoliticaTardia.choices, default=PoliticaTardia.NO_ACEPTA)
    penalidad_puntos = models.DecimalField(max_digits=4, decimal_places=2, default=0)  # puntos que se restan si es tardía
    tipo_calificacion = models.CharField(max_length=10, choices=TipoCalificacion.choices, default=TipoCalificacion.NOTA)
    tipo = models.CharField(max_length=10, choices=TipoTarea.choices, default=TipoTarea.INDIVIDUAL)
    creado = models.DateTimeField(default=timezone.now)
    eliminado = models.DateTimeField(null=True, blank=True)  # en la papelera

    objects = ActivosManager()
    todos = models.Manager()

    class Meta:
        verbose_name = "tarea"
        verbose_name_plural = "tareas"
        ordering = ["-fecha_limite", "id"]
        base_manager_name = "todos"

    def __str__(self):
        return self.titulo

    @property
    def modulo(self):
        return self.clase.modulo

    @property
    def vencida(self):
        return self.fecha_limite < timezone.now()

    @property
    def acepta_entregas(self):
        """¿El alumno todavía puede entregar? (la clase debe estar abierta)"""
        if self.clase.situacion != "abierta":
            return False
        return not self.vencida or self.politica_tardia != PoliticaTardia.NO_ACEPTA

    @property
    def de_clase_proxima(self):
        """¿La clase de esta tarea todavía no empieza? (el alumno no la ve)"""
        return self.clase.situacion == "proxima"

    @property
    def texto_tardia(self):
        if self.politica_tardia == PoliticaTardia.NO_ACEPTA:
            return "Después de la fecha ya no se acepta."
        if self.politica_tardia == PoliticaTardia.ACEPTA:
            return "Si entregas tarde igual se acepta."
        return f"Si entregas tarde se restan {nota_fmt(self.penalidad_puntos)} puntos."

    @property
    def lista_criterios(self):
        return criterios_de_texto(self.criterios)


def criterios_de_texto(texto):
    """Criterios de una tarea: una línea por criterio, «texto|puntos» (los puntos son opcionales)."""
    resultado = []
    for linea in (texto or "").splitlines():
        t, _, p = linea.strip().partition("|")
        t, p = t.strip(), p.strip()
        if t:
            resultado.append({"texto": t, "puntos": int(p) if p.isdigit() else None})
    return resultado


@borra_archivos("archivo_ruta", "retro_ruta")
class Entrega(models.Model):
    tarea = models.ForeignKey(Tarea, on_delete=models.CASCADE, related_name="entregas")
    alumno = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entregas")
    archivo_ruta = models.CharField(max_length=255, blank=True, default="")
    archivo_nombre = models.CharField(max_length=255, blank=True, default="")
    enlace = models.CharField(max_length=500, blank=True, default="")
    comentario_alumno = models.TextField(blank=True, default="")
    fecha_entrega = models.DateTimeField(default=timezone.now)
    tardia = models.BooleanField(default=False)
    nota = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)  # 'nota' y 'rubrica' (0–20)
    aprobado = models.BooleanField(null=True, blank=True)  # 'aprobado'
    comentario_docente = models.TextField(blank=True, default="")
    calificado = models.DateTimeField(null=True, blank=True)
    retro_ruta = models.CharField(max_length=255, blank=True, default="")  # archivo o foto que devuelve el docente
    retro_nombre = models.CharField(max_length=255, blank=True, default="")
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "entrega"
        verbose_name_plural = "entregas"
        constraints = [models.UniqueConstraint(fields=["tarea", "alumno"], name="entrega_unica")]
        ordering = ["fecha_entrega"]

    def __str__(self):
        return f"{self.alumno} → {self.tarea}"

    @property
    def calificada(self):
        return self.nota is not None or self.aprobado is not None

    @property
    def es_imagen(self):
        return bool(self.archivo_ruta) and Path(self.archivo_ruta).suffix.lower().lstrip(".") in ("jpg", "jpeg", "png", "webp")

    @property
    def resultado_texto(self):
        if self.nota is not None:
            return f"Nota {nota_fmt(self.nota)}"
        return "Aprobó" if self.aprobado else "No aprobó"

    @staticmethod
    def sin_calificar():
        return Entrega.objects.filter(nota__isnull=True, aprobado__isnull=True)

    def siguiente_sin_calificar(self):
        """Siguiente entrega sin calificar de la misma tarea (para «Guardar y ver el siguiente»)."""
        return (
            Entrega.objects.filter(tarea=self.tarea, nota__isnull=True, aprobado__isnull=True)
            .exclude(pk=self.pk)
            .order_by("fecha_entrega")
            .first()
        )


def es_enlace_valido(texto):
    """Una dirección web completa que empieza con http:// o https://"""
    return bool(re.match(r"https?://[^\s/$.?#][^\s]*$", texto or "", re.I))
