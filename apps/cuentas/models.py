"""Cuentas de usuario del aula virtual.

Una sola tabla para las cuatro clases de persona (administrador, dirección, docente y alumno),
igual que en el sistema anterior. Los alumnos entran con DNI; el resto con correo.
Lo que antes estaba en `av_perfiles` (origen, fecha de nacimiento, cambio de clave) ahora vive aquí.
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


class Origen(models.TextChoices):
    ADMIN = "admin", "Creada por el administrador"
    LISTA = "lista", "Cargada desde una lista"
    REGISTRO = "registro", "Creada por el alumno"


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, correo, password, **extra):
        if correo:
            correo = self.normalize_email(correo).lower()
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

    def crear_alumno(
        self, dni, nombres, apellidos, clave=None, origen=Origen.LISTA, telefono="", correo=None, fecha_nacimiento=None
    ):
        """Crea un alumno. Sin `clave` queda «pendiente»: entra cuando escribe su DNI en «Crear mi cuenta»."""
        alumno = self._crear(
            correo,
            clave,
            dni=dni,
            nombres=nombres,
            apellidos=apellidos,
            telefono=telefono or "",
            fecha_nacimiento=fecha_nacimiento,
            origen=origen,
            rol=Rol.ALUMNO,
        )
        if clave:
            alumno.activado = timezone.now()
            alumno.save(update_fields=["activado"])
        return alumno

    def docentes(self):
        return self.filter(rol=Rol.DOCENTE, is_active=True).order_by("apellidos", "nombres")

    def buscar_para_entrar(self, texto):
        """Busca por correo (si trae «@») o por DNI (8 números). Devuelve None si no hay."""
        texto = (texto or "").strip()
        if "@" in texto:
            return self.filter(correo__iexact=texto).first()
        dni = "".join(c for c in texto if c.isdigit())
        return self.filter(dni=dni).first() if len(dni) == 8 else None


class Usuario(AbstractBaseUser, PermissionsMixin):
    dni = models.CharField(max_length=8, unique=True, null=True, blank=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100, blank=True, default="")
    correo = models.EmailField(max_length=120, unique=True, null=True, blank=True)
    telefono = models.CharField("celular", max_length=15, blank=True, default="")
    fecha_nacimiento = models.DateField(null=True, blank=True)
    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.ALUMNO)
    origen = models.CharField(max_length=10, choices=Origen.choices, default=Origen.ADMIN)
    debe_cambiar_clave = models.BooleanField(
        "debe elegir su contraseña al entrar", default=False, help_text="La que le dieron era temporal."
    )
    activado = models.DateTimeField("cuándo creó su contraseña", null=True, blank=True)
    tutorial_visto = models.DateTimeField(
        "cuándo vio el tutorial", null=True, blank=True, help_text="Vacío = el tutorial se le muestra la primera vez que entra."
    )
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
    def primer_nombre(self):
        return (self.nombres.split() or [self.nombres])[0]

    @property
    def iniciales(self):
        return (self.nombres[:1] + self.apellidos[:1]).upper()

    @property
    def identificador(self):
        """Cómo se identifica la cuenta: su correo, o su DNI si no tiene correo."""
        if self.correo:
            return self.correo
        return f"DNI {self.dni}" if self.dni else ""

    @property
    def pendiente(self):
        """Alumno cargado en una lista que todavía no creó su contraseña."""
        return not self.has_usable_password()

    def activar(self, clave, telefono=""):
        """El alumno de la lista crea su contraseña (y puede dejar su celular)."""
        self.set_password(clave)
        self.activado = timezone.now()
        if telefono:
            self.telefono = telefono
        self.save(update_fields=["password", "activado", "telefono"])

    def dar_clave(self, clave, forzar=False):
        """Le da una contraseña nueva (la anterior deja de servir). Con `forzar`, la persona elige la suya al entrar.
        Si era un alumno de lista que todavía no tenía contraseña, queda activado."""
        era_pendiente = self.pendiente
        self.set_password(clave)
        self.debe_cambiar_clave = forzar
        if era_pendiente:
            self.activado = timezone.now()
        self.save(update_fields=["password", "debe_cambiar_clave", "activado"])

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

    @property
    def preferencias(self):
        """Preferencias de accesibilidad (con valores por defecto si todavía no las guardó)."""
        try:
            return self.preferencia
        except Preferencia.DoesNotExist:
            return Preferencia(usuario=self)


class TamanoLetra(models.TextChoices):
    NORMAL = "normal", "Normal"
    GRANDE = "grande", "Grande"
    MUY_GRANDE = "muy_grande", "Muy grande"


class Preferencia(models.Model):
    """Preferencias de accesibilidad de cada persona."""

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name="preferencia")
    tamano_letra = models.CharField(max_length=10, choices=TamanoLetra.choices, default=TamanoLetra.NORMAL)
    alto_contraste = models.BooleanField(default=False)
    lectura_voz = models.BooleanField(default=False)
    modo_asistente = models.CharField(max_length=10, choices=[("escrito", "Escrito"), ("voz", "Voz")], default="escrito")
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "preferencia"
        verbose_name_plural = "preferencias"

    def __str__(self):
        return f"Preferencias de {self.usuario}"
