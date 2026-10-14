"""Respaldo de la base de datos (PostgreSQL) y de los archivos subidos.

- La base se guarda con `pg_dump` en formato «custom» (comprimido): `base_AAAA-MM-DD_HHMMSS.dump`.
- Los archivos subidos (fotos, trabajos, materiales) se guardan en un `.zip`: `archivos_AAAA-MM-DD_HHMMSS.zip`.
- Se escribe primero con un nombre temporal; un respaldo a medias nunca queda como si estuviera completo.
- Se conservan los más recientes de cada tipo (por defecto 14).
La contraseña de la base viaja en una variable de entorno de ese proceso, nunca en la línea de comandos.
Para volver a poner un respaldo: `pg_restore --clean --if-exists --no-owner -d NOMBRE_DE_LA_BASE archivo.dump`."""

import glob
import os
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection

CONSERVAR = 14
PATRONES = {"base": "base_*.dump", "archivos": "archivos_*.zip"}


class RespaldoError(Exception):
    """Mensaje listo para mostrar a la persona."""


def carpeta_de_respaldos(carpeta=None):
    return Path(carpeta or settings.RESPALDOS_CARPETA)


def buscar_pg_dump():
    """Dónde está `pg_dump`: la variable PG_DUMP, el PATH o la carpeta normal de PostgreSQL en Windows."""
    indicado = os.environ.get("PG_DUMP")
    if indicado:
        if Path(indicado).is_file():
            return indicado
        raise RespaldoError(f"La variable PG_DUMP apunta a «{indicado}», pero ese archivo no existe.")
    en_el_path = shutil.which("pg_dump")
    if en_el_path:
        return en_el_path
    candidatos = sorted(glob.glob(r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe"), reverse=True)
    if candidatos:
        return candidatos[0]
    raise RespaldoError(
        "No encuentro «pg_dump» (viene con PostgreSQL). Agrega la carpeta «bin» de PostgreSQL al PATH "
        "o escribe su ruta completa en la variable de entorno PG_DUMP."
    )


def _estampa():
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def respaldar_base(carpeta, estampa=None):
    """Guarda la base con pg_dump. Devuelve la ruta del archivo."""
    cfg = connection.settings_dict
    final = carpeta / f"base_{estampa or _estampa()}.dump"
    parcial = final.with_suffix(".dump.parte")
    orden = [
        buscar_pg_dump(),
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--file={parcial}",
        f"--host={cfg.get('HOST') or 'localhost'}",
        f"--port={cfg.get('PORT') or 5432}",
        f"--username={cfg['USER']}",
        cfg["NAME"],
    ]
    entorno = {**os.environ, "PGPASSWORD": cfg.get("PASSWORD") or ""}
    try:
        r = subprocess.run(orden, env=entorno, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    except OSError as e:
        raise RespaldoError(f"No se pudo ejecutar pg_dump: {e}") from e
    if r.returncode != 0:
        parcial.unlink(missing_ok=True)
        raise RespaldoError(f"pg_dump falló: {(r.stderr or r.stdout).strip()[:500]}")
    parcial.replace(final)
    return final


def respaldar_archivos(carpeta, estampa=None):
    """Guarda en un .zip todos los archivos subidos. Devuelve (ruta, cantidad de archivos)."""
    origen = Path(settings.MEDIA_ROOT)
    final = carpeta / f"archivos_{estampa or _estampa()}.zip"
    parcial = final.with_suffix(".zip.parte")
    cantidad = 0
    try:
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as z:
            if origen.is_dir():
                for archivo in sorted(origen.rglob("*")):
                    if archivo.is_file():
                        z.write(archivo, archivo.relative_to(origen).as_posix())
                        cantidad += 1
    except OSError as e:
        parcial.unlink(missing_ok=True)
        raise RespaldoError(f"No se pudo guardar el zip de archivos: {e}") from e
    parcial.replace(final)
    return final, cantidad


def dejar_los_recientes(carpeta, conservar=CONSERVAR):
    """Borra los respaldos más viejos de cada tipo y deja `conservar`. Devuelve cuántos borró."""
    borrados = 0
    for patron in PATRONES.values():
        lista = sorted(carpeta.glob(patron), reverse=True)  # el nombre lleva la fecha: el más nuevo primero
        for viejo in lista[conservar:]:
            viejo.unlink(missing_ok=True)
            borrados += 1
    return borrados


def respaldar(con_archivos=False, carpeta=None, conservar=CONSERVAR):
    """Hace el respaldo. Devuelve {'base': ruta, 'archivos': (ruta, cantidad) | None, 'borrados': n}."""
    destino = carpeta_de_respaldos(carpeta)
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RespaldoError(f"No se pudo crear la carpeta de respaldos {destino}: {e}") from e
    estampa = _estampa()
    resultado = {"base": respaldar_base(destino, estampa), "archivos": None}
    if con_archivos:
        resultado["archivos"] = respaldar_archivos(destino, estampa)
    resultado["borrados"] = dejar_los_recientes(destino, conservar)
    return resultado
