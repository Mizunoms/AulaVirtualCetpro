"""Configuración de Django para el Aula Virtual CETPRO Mangomarca.

Todo lo que cambia entre la PC de desarrollo y el servidor se lee del archivo .env
(ver .env.example). Aquí no se escriben claves.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    FORCE_SCRIPT_NAME=(str, ""),
    SESSION_COOKIE_SECURE=(bool, False),
    URL_BASE=(str, ""),
    ARCHIVOS_MAX_MB=(int, 10),
    ARCHIVOS_CARPETA=(str, ""),
    RESPALDOS_CARPETA=(str, ""),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# Si el aula se publica dentro de un sitio (ej. https://servidor/aula), poner FORCE_SCRIPT_NAME=/aula
FORCE_SCRIPT_NAME = env("FORCE_SCRIPT_NAME") or None

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.cuentas",
    "apps.nucleo",
    "apps.academico",
    "apps.tareas",
    "apps.evaluacion",
    "apps.mensajes",
    "apps.formularios",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.nucleo.middleware.CabecerasSeguridad",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.nucleo.contexto.aula",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Base de datos: PostgreSQL. Ejemplo: postgres://aula_app:CLAVE@localhost:5432/aula_virtual_cetpro
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60

AUTH_USER_MODEL = "cuentas.Usuario"
AUTHENTICATION_BACKENDS = ["apps.cuentas.backends.DniOCorreoBackend"]

# Las contraseñas nuevas se guardan con PBKDF2 (el primero). Las bcrypt del sistema anterior ($2y$…) siguen sirviendo
# y se vuelven a guardar con PBKDF2 la primera vez que la persona entra.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "cuentas:login"
LOGIN_REDIRECT_URL = "nucleo:inicio"
LOGOUT_REDIRECT_URL = "cuentas:login"

# Las direcciones del aula no llevan «/» al final (igual que en el sistema anterior).
APPEND_SLASH = False

# Un mensaje «ok» o «error» (igual que en el sistema anterior)
from django.contrib.messages import constants as _m  # noqa: E402

MESSAGE_TAGS = {_m.SUCCESS: "ok", _m.ERROR: "error"}
CSRF_FAILURE_VIEW = "apps.nucleo.views.error_csrf"

# Dirección pública del aula (ej. https://servidor.ts.net/aula). Vacío = se detecta sola.
URL_BASE = env("URL_BASE")

LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

# Con FORCE_SCRIPT_NAME (ej. /aula) la dirección de los estilos y scripts debe llevar ese prefijo desde el principio:
# si no, Django la calcula antes de conocer el prefijo y los enlaces salen sin él.
STATIC_URL = (FORCE_SCRIPT_NAME or "").rstrip("/") + "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Archivos subidos por docentes y alumnos: fuera de la carpeta pública, se sirven con permisos.
# (Se puede cambiar con ARCHIVOS_CARPETA en el .env, por ejemplo una carpeta aparte en el servidor.)
MEDIA_ROOT = Path(env("ARCHIVOS_CARPETA")) if env("ARCHIVOS_CARPETA") else BASE_DIR / "storage" / "uploads"

# Respaldos de la base y de los archivos (manage.py respaldo). Mejor en otro disco que los datos.
RESPALDOS_CARPETA = Path(env("RESPALDOS_CARPETA")) if env("RESPALDOS_CARPETA") else BASE_DIR / "storage" / "respaldos"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Archivos que se pueden subir (se comprueba también su contenido real)
ARCHIVOS_MAX_MB = env("ARCHIVOS_MAX_MB")
ARCHIVOS_EXTENSIONES = ["jpg", "jpeg", "png", "webp", "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx"]
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

# Seguridad de sesión y cookies
SESSION_COOKIE_NAME = "aula_cetpro"
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 horas, para que nadie pierda un examen o un formulario largo
SESSION_COOKIE_SECURE = env("SESSION_COOKIE_SECURE")
# Si el aula vive en /aula, sus cookies de sesión no se mandan al resto del sitio del CETPRO
SESSION_COOKIE_PATH = FORCE_SCRIPT_NAME.rstrip("/") + "/" if FORCE_SCRIPT_NAME else "/"
CSRF_COOKIE_PATH = SESSION_COOKIE_PATH
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
