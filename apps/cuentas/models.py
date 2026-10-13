"""Cuentas de usuario del aula virtual.

Una sola tabla para las cuatro clases de persona (administrador, dirección, docente y alumno),
igual que en el sistema anterior. Los alumnos entran con DNI; el resto con correo.
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class Rol(models.TextChoices):
    ADMIN = "admin", "Administrador"
    DIRECCION = "direccion", "Dirección"
    DOCENTE = "docente", "Docente"
    ALUMNO = "alumno", "Alumno"


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, correo, password, **extra):
        if correo:
            correo = self.normalize_email(correo)
        usuario = self.model(correo=correo or None, **extra)
        if password:
            usuario.set_password(password)
        else:
            # Alumno cargado desde una lista que todavía no creó su contraseña.
            usuario.set_unusable_password()
        usuario.save(using=self._db)
        return usuario

    def create_user(self, correo=None, password=None, **extra):
        extra.setdefault("rol", Rol.ALUMNO)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(correo, password, **extra)

    def create_superuser(self, correo, password=None, **extra):
        extra.setdefault("rol", Rol.ADMIN)
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._crear(correo, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    dni = models.CharField(max_length=8, unique=True, null=True, blank=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100, blank=True, default="")
    correo = models.EmailField(max_length=120, unique=True, null=True, blank=True)
    telefono = models.CharField("celular", max_length=15, blank=True, default="")
    fecha_nacimiento = models.DateField(null=True, blank=True)
    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.ALUMNO)
    is_active = models.BooleanField("activo", default=True)
    is_staff = models.BooleanField("puede entrar al panel de Django", default=False)
    creado = models.DateTimeField(default=timezone.now)

    objects = UsuarioManager()

    USERNAME_FIELD = "correo"
    REQUIRED_FIELDS = ["nombres"]

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return self.nombre_completo or self.correo or self.dni or f"Usuario {self.pk}"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def es_alumno(self):
        return self.rol == Rol.ALUMNO

    @property
    def es_docente(self):
        return self.rol == Rol.DOCENTE

    @property
    def es_admin(self):
        return self.rol == Rol.ADMIN

    @property
    def es_direccion(self):
        return self.rol == Rol.DIRECCION
