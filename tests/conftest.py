import pytest
from django.core.cache import cache
from django.test import Client

from apps.cuentas.models import Rol, Usuario

pytest_plugins = ["tests.formularios_comun"]

CLAVE = "clave-prueba-1"


@pytest.fixture(autouse=True)
def _entorno_de_prueba(settings, tmp_path):
    """Cada prueba empieza limpia: sin caché de ajustes, sin archivos reales y con css simple."""
    cache.clear()
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # rápido; solo para pruebas
    settings.MEDIA_ROOT = tmp_path / "uploads"  # nunca se toca la carpeta real de archivos
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


def _crear(rol, **datos):
    return Usuario.objects.create_user(password=CLAVE, rol=rol, **datos)


@pytest.fixture
def alumno(db):
    return _crear(Rol.ALUMNO, dni="12345678", nombres="Rosa", apellidos="Quispe Mamani")


@pytest.fixture
def docente(db):
    return _crear(Rol.DOCENTE, correo="maria@cetpro.com", nombres="María", apellidos="Torres")


@pytest.fixture
def admin(db):
    return _crear(Rol.ADMIN, correo="admin@cetpro.com", nombres="Ana", apellidos="Directora")


@pytest.fixture
def cliente_de():
    """Devuelve un cliente de pruebas con la sesión iniciada como esa persona."""

    def _cliente(usuario):
        c = Client()
        c.force_login(usuario)
        return c

    return _cliente
