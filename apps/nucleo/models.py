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
