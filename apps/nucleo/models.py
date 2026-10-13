"""Núcleo: ajustes del CETPRO, registro de actividad e intentos de acceso."""

from django.conf import settings
from django.db import models


class Ajuste(models.Model):
    """Ajustes del aula que cambia el administrador (colores, logo, textos, especialidades…)."""

    clave = models.CharField(max_length=60, primary_key=True)
    valor = models.TextField()
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ajuste"
        verbose_name_plural = "ajustes"

    def __str__(self):
        return self.clave


class Registro(models.Model):
    """Registro de actividad: quién hizo qué. Nunca guarda contraseñas."""

    ACCIONES = {
        "acceso": "Accesos",
        "clave": "Contraseñas",
        "cuenta": "Cuentas",
        "notas": "Notas y asistencia",
        "ajustes": "Ajustes",
        "modulo": "Módulos",
    }

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    accion = models.CharField(max_length=30)
    detalle = models.CharField(max_length=255)
    ip = models.CharField(max_length=45, blank=True, default="")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "movimiento"
        verbose_name_plural = "registro de actividad"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["creado"], name="registro_fecha_idx"),
            models.Index(fields=["accion", "creado"], name="registro_accion_idx"),
        ]

    def __str__(self):
        return f"{self.accion}: {self.detalle}"

    @classmethod
    def anotar(cls, actor, accion, detalle, request=None):
        """Anota una acción. `actor` es quien la hizo (o None). Si falla, no interrumpe lo que se hacía."""
        from .utils import ip_cliente

        try:
            cls.objects.create(
                usuario=actor if getattr(actor, "pk", None) else None,
                accion=accion,
                detalle=detalle[:255],
                ip=ip_cliente(request)[:45] if request is not None else "",
            )
        except Exception:  # noqa: BLE001 - el registro nunca debe romper la acción principal
            pass


class Notificacion(models.Model):
    """Avisos dentro del aula (la campana): nueva tarea, te calificaron, nuevo aviso del profesor…"""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones")
    mensaje = models.CharField(max_length=255)
    enlace = models.CharField(max_length=255, blank=True, default="")
    leida = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "notificación"
        verbose_name_plural = "notificaciones"
        ordering = ["-id"]
        indexes = [models.Index(fields=["usuario", "leida", "creado"], name="notif_usuario_idx")]

    def __str__(self):
        return self.mensaje

    @staticmethod
    def _relativo(enlace):
        """Se guarda sin la carpeta donde está instalada el aula (ej. «/aula»), para que no dependa de ella."""
        from django.urls import get_script_prefix

        prefijo = get_script_prefix().rstrip("/")
        return enlace[len(prefijo) :] if prefijo and enlace.startswith(prefijo + "/") else enlace

    @property
    def enlace_url(self):
        from django.urls import get_script_prefix

        return get_script_prefix().rstrip("/") + (self.enlace or "/")

    @classmethod
    def crear(cls, usuario, mensaje, enlace=""):
        return cls.objects.create(usuario=usuario, mensaje=mensaje[:255], enlace=cls._relativo(enlace)[:255])

    @classmethod
    def a_alumnos(cls, modulo, mensaje, enlace=""):
        """El mismo aviso para todos los alumnos activos de un módulo."""
        relativo = cls._relativo(enlace)[:255]
        cls.objects.bulk_create([cls(usuario=a, mensaje=mensaje[:255], enlace=relativo) for a in modulo.alumnos()])

    @classmethod
    def sin_leer(cls, usuario):
        return cls.objects.filter(usuario=usuario, leida=False).count()

    @classmethod
    def marcar_leidas(cls, usuario):
        import random
        from datetime import timedelta

        from django.utils import timezone

        cls.objects.filter(usuario=usuario, leida=False).update(leida=True)
        if random.randint(1, 20) == 1:  # limpieza ocasional de lo viejo
            cls.objects.filter(leida=True, creado__lt=timezone.now() - timedelta(days=90)).delete()


class IntentoAcceso(models.Model):
    """Intentos fallidos de entrar o registrarse (para frenar a quien prueba contraseñas o códigos).

    Se guarda en la base (no en la sesión) para que no se pueda saltar abriendo otra ventana.
    """

    clave = models.CharField(max_length=100)  # ej. login:12345678, login-ip:1.2.3.4
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["clave", "creado"], name="acceso_clave_idx")]

    def __str__(self):
        return self.clave
