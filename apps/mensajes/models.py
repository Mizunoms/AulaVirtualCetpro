"""Mensajes privados entre un alumno y el docente de su módulo."""

from django.conf import settings
from django.db import models, transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.signals import post_delete
from django.utils import timezone

from apps.academico.models import Modulo
from apps.nucleo import archivos


class Conversacion(models.Model):
    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE, related_name="conversaciones")
    docente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversaciones_docente")
    alumno = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversaciones_alumno")
    actualizado = models.DateTimeField(default=timezone.now)
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "conversación"
        verbose_name_plural = "conversaciones"
        constraints = [models.UniqueConstraint(fields=["modulo", "docente", "alumno"], name="conversacion_unica")]

    def __str__(self):
        return f"{self.docente} ↔ {self.alumno} ({self.modulo})"

    def otro(self, usuario):
        """La otra persona de la conversación."""
        return self.alumno if usuario.pk == self.docente_id else self.docente

    @classmethod
    def de_usuario(cls, usuario, modulo=None):
        """Conversaciones de la persona (de un módulo, o de todos), con el último mensaje y cuántos no leyó.
        La que tiene el mensaje más reciente va primero."""
        ultimos = Mensaje.objects.filter(conversacion=OuterRef("pk")).order_by("-id")
        consulta = cls.objects.filter(Q(docente=usuario) | Q(alumno=usuario))
        if modulo is not None:
            consulta = consulta.filter(modulo=modulo)
        consulta = (
            consulta.select_related("modulo", "docente", "alumno")
            .annotate(
                ultimo_texto=Subquery(ultimos.values("texto")[:1]),
                ultimo_fecha=Subquery(ultimos.values("creado")[:1]),
                ultimo_autor=Subquery(ultimos.values("autor_id")[:1]),
                sin_leer=Count("mensajes", filter=Q(mensajes__leido__isnull=True) & ~Q(mensajes__autor=usuario)),
            )
            .order_by(models.F("ultimo_fecha").desc(nulls_last=True), "-id")
        )
        lista = list(consulta)
        for cv in lista:
            cv.otro_usuario = cv.otro(usuario)
        return lista

    @classmethod
    def obtener_o_crear(cls, modulo, docente, alumno):
        """La conversación entre el docente y el alumno de un módulo (se crea si todavía no existe).
        `docente` y `alumno` pueden ser la persona o su número (id)."""
        cv, _creada = cls.objects.get_or_create(
            modulo=modulo, docente_id=getattr(docente, "pk", docente), alumno_id=getattr(alumno, "pk", alumno)
        )
        return cv

    def enviar(self, autor, texto, archivo=None):
        """Envía un mensaje. `archivo` es (ruta, nombre) o None."""
        ruta, nombre = archivo or ("", "")
        mensaje = Mensaje.objects.create(conversacion=self, autor=autor, texto=texto, archivo_ruta=ruta, archivo_nombre=nombre)
        Conversacion.objects.filter(pk=self.pk).update(actualizado=timezone.now())
        return mensaje

    def marcar_leidos(self, lector):
        """Marca como leídos los mensajes que la otra persona le escribió a `lector`."""
        self.mensajes.exclude(autor=lector).filter(leido__isnull=True).update(leido=timezone.now())


class Mensaje(models.Model):
    conversacion = models.ForeignKey(Conversacion, on_delete=models.CASCADE, related_name="mensajes")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mensajes_enviados")
    texto = models.TextField(blank=True, default="")
    leido = models.DateTimeField(null=True, blank=True)
    archivo_ruta = models.CharField(max_length=255, blank=True, default="")  # foto o archivo adjunto
    archivo_nombre = models.CharField(max_length=255, blank=True, default="")
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "mensaje"
        verbose_name_plural = "mensajes"
        ordering = ["id"]
        indexes = [models.Index(fields=["conversacion", "creado"], name="mensaje_conv_idx")]

    def __str__(self):
        return self.texto[:60] or "Archivo adjunto"

    @classmethod
    def sin_leer(cls, usuario):
        """Cuántos mensajes le escribieron a la persona y todavía no leyó."""
        return (
            cls.objects.filter(Q(conversacion__docente=usuario) | Q(conversacion__alumno=usuario), leido__isnull=True)
            .exclude(autor=usuario)
            .count()
        )


def _borrar_adjunto(sender, instance, **kwargs):
    """Al eliminar un mensaje se borra su archivo, salvo que otro mensaje lo siga usando
    (el «mensaje a todos» guarda un solo archivo para todos los alumnos)."""
    ruta = instance.archivo_ruta
    if ruta:
        transaction.on_commit(lambda: None if Mensaje.objects.filter(archivo_ruta=ruta).exists() else archivos.borrar(ruta))


post_delete.connect(_borrar_adjunto, sender=Mensaje, weak=False, dispatch_uid="borrar_adjunto_mensaje")
