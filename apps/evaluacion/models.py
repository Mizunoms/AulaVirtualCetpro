"""Asistencia: cada día de clase (sesión) y si cada alumno vino, llegó tarde, faltó o justificó."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.academico.models import Modulo


class SesionAsistencia(models.Model):
    """Un día de clase de un módulo."""

    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE, related_name="sesiones")
    fecha = models.DateField()
    tema = models.CharField(max_length=200, blank=True, default="")
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "día de asistencia"
        verbose_name_plural = "días de asistencia"
        constraints = [models.UniqueConstraint(fields=["modulo", "fecha"], name="sesion_unica")]
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.modulo} · {self.fecha}"


class Estado(models.TextChoices):
    PRESENTE = "presente", "Vino"
    TARDE = "tarde", "Tarde"
    FALTA = "falta", "Faltó"
    JUSTIFICADA = "justificada", "Justificó"


class Asistencia(models.Model):
    sesion = models.ForeignKey(SesionAsistencia, on_delete=models.CASCADE, related_name="asistencias")
    alumno = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="asistencias")
    estado = models.CharField(max_length=12, choices=Estado.choices)
    observacion = models.CharField(max_length=255, blank=True, default="")
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "asistencia"
        verbose_name_plural = "asistencias"
        constraints = [models.UniqueConstraint(fields=["sesion", "alumno"], name="asistencia_unica")]

    def __str__(self):
        return f"{self.alumno} {self.estado}"

    @property
    def vino(self):
        """Tarde y justificada cuentan como asistencia."""
        return self.estado in (Estado.PRESENTE, Estado.TARDE, Estado.JUSTIFICADA)


def porcentajes(modulo):
    """{alumno_id: {"total", "vino", "pct"}}: porcentaje de clases a las que vino (tarde y justificada cuentan)."""
    filas = (
        Asistencia.objects.filter(sesion__modulo=modulo)
        .values("alumno_id")
        .annotate(
            total=models.Count("id"),
            vino=models.Count("id", filter=models.Q(estado__in=[Estado.PRESENTE, Estado.TARDE, Estado.JUSTIFICADA])),
        )
    )
    return {
        f["alumno_id"]: {"total": f["total"], "vino": f["vino"], "pct": _redondear(100 * f["vino"] / max(1, f["total"]))}
        for f in filas
    }


def _redondear(x):
    from decimal import ROUND_HALF_UP, Decimal

    return int(Decimal(str(x)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def historial_alumno(modulo, alumno):
    """Historial de un alumno en un módulo, más reciente primero."""
    return list(
        Asistencia.objects.filter(sesion__modulo=modulo, alumno=alumno).select_related("sesion").order_by("-sesion__fecha")
    )


def sesiones_recientes(modulo, limite=10):
    """Clases anteriores con cuántos faltaron."""
    return list(
        SesionAsistencia.objects.filter(modulo=modulo)
        .annotate(
            faltaron=models.Count("asistencias", filter=models.Q(asistencias__estado=Estado.FALTA)),
            total=models.Count("asistencias"),
        )
        .order_by("-fecha")[:limite]
    )


def tomada_hoy(modulo):
    return Asistencia.objects.filter(sesion__modulo=modulo, sesion__fecha=timezone.localdate()).exists()


def registrados_hoy(modulo):
    return Asistencia.objects.filter(sesion__modulo=modulo, sesion__fecha=timezone.localdate()).count()
