"""Prueba de aceptación: corre los guiones HTTP del sistema anterior (carpeta `guiones/`) contra este sistema.

Arma una base de datos PROPIA («…_aceptacion», nunca la de trabajo), carga los datos de prueba del sistema anterior, levanta un
servidor en http://127.0.0.1:8090 y corre cada guion con la base recién armada, como hacía `tests/correr.sh` del sistema anterior.

Uso (con el entorno virtual activado, desde la carpeta del proyecto):
    python aceptacion/correr.py                 → todos los guiones
    python aceptacion/correr.py test_version2   → solo ese
Los resultados completos quedan en aceptacion/.tmp/salida-<guion>.txt
"""

import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg

RAIZ = Path(__file__).resolve().parent.parent
TMP = Path(__file__).resolve().parent / ".tmp"
PUERTO = 8090
BASE = f"http://127.0.0.1:{PUERTO}"
GUIONES = ["test_version2", "test_general", "test_importar", "test_mensajes"]


def leer_env():
    datos = {}
    archivo = RAIZ / ".env"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                datos[k.strip()] = v.strip().strip('"').strip("'")
    return datos


def url_de_aceptacion():
    original = os.environ.get("DATABASE_URL") or leer_env().get("DATABASE_URL")
    if not original:
        sys.exit("No encuentro DATABASE_URL (ni en el entorno ni en .env).")
    partes = urlsplit(original)
    nombre = "aula_virtual_aceptacion"  # una base propia: nunca la de trabajo
    return urlunsplit(partes._replace(path="/" + nombre)), urlunsplit(partes._replace(path="/postgres")), nombre


def preparar_base(env, url_servidor, nombre):
    """Borra y crea la base de aceptación, migra y carga los datos de prueba del sistema anterior."""
    with psycopg.connect(url_servidor.replace("postgres://", "postgresql://"), autocommit=True) as con:
        con.execute(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')
        con.execute(f"CREATE DATABASE \"{nombre}\" ENCODING 'UTF8'")
    shutil.rmtree(TMP / "archivos", ignore_errors=True)
    (TMP / "archivos").mkdir(parents=True, exist_ok=True)
    for orden in (["migrate", "--noinput"], ["datos_aceptacion"]):
        r = subprocess.run(
            [sys.executable, "manage.py", *orden], cwd=RAIZ, env=env, capture_output=True, text=True, encoding="utf-8"
        )
        if r.returncode != 0:
            sys.exit(f"Falló «manage.py {' '.join(orden)}»:\n{r.stdout}\n{r.stderr}")
    # Vistas con los nombres de tablas del sistema anterior, para los SELECT de sus guiones
    with psycopg.connect(env["DATABASE_URL"].replace("postgres://", "postgresql://"), autocommit=True) as con:
        con.execute((Path(__file__).resolve().parent / "vistas_php.sql").read_text(encoding="utf-8"))


def levantar_servidor(env):
    log = open(TMP / "servidor.log", "w", encoding="utf-8")
    proceso = subprocess.Popen(
        [sys.executable, "-m", "waitress", f"--listen=127.0.0.1:{PUERTO}", "--threads=4", "config.wsgi:application"],
        cwd=RAIZ, env=env, stdout=log, stderr=subprocess.STDOUT,
    )  # fmt: skip
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/login", timeout=2)
            return proceso
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    proceso.terminate()
    sys.exit("El servidor no arrancó. Mira aceptacion/.tmp/servidor.log")


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    url_base, url_servidor, nombre = url_de_aceptacion()
    env = {
        **os.environ,
        "DATABASE_URL": url_base,
        "ARCHIVOS_CARPETA": str(TMP / "archivos"),
        "DEBUG": "False",
        "PYTHONIOENCODING": "utf-8",
        "BASE": BASE,
    }
    elegidos = [a for a in sys.argv[1:] if a in GUIONES] or GUIONES
    subprocess.run(
        [sys.executable, "manage.py", "collectstatic", "--noinput"], cwd=RAIZ, env=env, capture_output=True, check=False
    )
    mal = 0
    for guion in elegidos:
        preparar_base(env, url_servidor, nombre)
        servidor = levantar_servidor(env)
        try:
            r = subprocess.run(
                [sys.executable, "-X", "utf8", f"{guion}.py"], cwd=RAIZ / "aceptacion" / "guiones", env=env,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
            )  # fmt: skip
            salida = r.stdout + r.stderr
        finally:
            servidor.terminate()
            servidor.wait(timeout=15)
        (TMP / f"salida-{guion}.txt").write_text(salida, encoding="utf-8")
        ok = len(re.findall(r"^  OK", salida, re.M))
        fallas = re.findall(r"^  (?:FALLA|!!!).*$", salida, re.M)
        if "FALLAS: 0" in salida:
            print(f"[OK]    {guion} ({ok} comprobaciones)")
        else:
            mal += 1
            print(f"[FALLA] {guion}: {ok} bien, {len(fallas)} con falla")
            for f in fallas[:80]:
                print("   ", f.strip()[:230])
    sys.exit(1 if mal else 0)


if __name__ == "__main__":
    main()
