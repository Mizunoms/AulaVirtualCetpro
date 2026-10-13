"""Subida y entrega segura de archivos.

- Valida extensión y tipo real (por el contenido del archivo, no por su nombre).
- Lo guarda con un nombre aleatorio fuera de la carpeta pública (`storage/uploads`).
"""

import secrets
import shutil
from datetime import date
from pathlib import Path

import filetype
from django.conf import settings
from django.http import FileResponse, Http404

IMAGENES = ("jpg", "jpeg", "png", "webp")

# Extensión → tipos reales aceptados (los de Office nuevos son archivos zip por dentro).
MIMES = {
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "png": {"image/png"},
    "webp": {"image/webp"},
    "heic": {"image/heic", "image/heif"},
    "pdf": {"application/pdf"},
    "doc": {"application/msword", "application/x-ole-storage", "application/CDFV2"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
    "ppt": {"application/vnd.ms-powerpoint", "application/x-ole-storage", "application/CDFV2"},
    "pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/zip"},
    "xls": {"application/vnd.ms-excel", "application/x-ole-storage", "application/CDFV2"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
}


class ArchivoError(Exception):
    """Mensaje listo para mostrar a la persona."""


def _base():
    return Path(settings.MEDIA_ROOT).resolve()


def _extensiones_permitidas():
    return [e for e in MIMES if e in set(settings.ARCHIVOS_EXTENSIONES) | {"heic"}]


def _tipo_real(cabecera, ext):
    tipo = filetype.guess(cabecera)
    return tipo.mime if tipo else ""


def guardar(subido):
    """Guarda un archivo subido (`request.FILES["campo"]`). Devuelve (ruta_relativa, nombre_original)."""
    if subido is None:
        raise ArchivoError("No se recibió el archivo.")
    max_mb = settings.ARCHIVOS_MAX_MB
    if subido.size > max_mb * 1024 * 1024:
        raise ArchivoError(f"El archivo es muy pesado. El máximo es {max_mb} MB.")
    ext = Path(subido.name).suffix.lower().lstrip(".")
    if ext not in _extensiones_permitidas():
        raise ArchivoError("Ese tipo de archivo no está permitido. Usa una foto, PDF, Word, Excel o PowerPoint.")
    cabecera = subido.read(4096)
    subido.seek(0)
    mime = _tipo_real(cabecera, ext)
    # Los Office antiguos (doc/xls/ppt) los reconoce `filetype` por su contenido; algunos zip de Office
    # se reconocen como zip. Ambos valen para su extensión.
    if mime not in MIMES[ext] and not (mime == "application/octet-stream" and ext in ("docx", "xlsx", "pptx")):
        raise ArchivoError("El archivo no parece ser lo que dice su nombre. Revisa que no esté dañado.")

    hoy = date.today()
    sub = f"{hoy.year}/{hoy.month:02d}"
    carpeta = _base() / sub
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"{secrets.token_hex(16)}.{ext}"
    with open(carpeta / nombre, "wb") as destino:
        for trozo in subido.chunks():
            destino.write(trozo)
    original = Path(subido.name.replace("\\", "/")).name[:200]
    return f"{sub}/{nombre}", original


def es_imagen(ruta):
    return bool(ruta) and Path(ruta).suffix.lower().lstrip(".") in IMAGENES


def _real(ruta):
    """Ruta real de un archivo guardado, solo si está dentro de la carpeta de subidas."""
    if not ruta:
        return None
    base = _base()
    real = (base / ruta).resolve()
    if base in real.parents and real.is_file():
        return real
    return None


def enviar(ruta, nombre_original, en_linea=False):
    """Respuesta con el archivo (ya se verificaron los permisos). 404 si ya no está."""
    real = _real(ruta)
    if real is None:
        raise Http404("El archivo ya no está disponible.")
    respuesta = FileResponse(open(real, "rb"), as_attachment=not en_linea, filename=nombre_original)
    respuesta["X-Content-Type-Options"] = "nosniff"
    respuesta["Cache-Control"] = "private, max-age=3600"
    return respuesta


def copiar(ruta):
    """Copia un archivo guardado (con otro nombre aleatorio). Devuelve la ruta nueva, o None si no existe."""
    real = _real(ruta)
    if real is None:
        return None
    hoy = date.today()
    sub = f"{hoy.year}/{hoy.month:02d}"
    carpeta = _base() / sub
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"{secrets.token_hex(16)}{real.suffix.lower()}"
    shutil.copy(real, carpeta / nombre)
    return f"{sub}/{nombre}"


def borrar(ruta):
    real = _real(ruta)
    if real is not None:
        real.unlink(missing_ok=True)
