"""Publicar el aula dentro de un sitio (https://servidor/aula) detrás de IIS: direcciones y cookies con el prefijo."""

import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

CODIGO = (
    "import json, django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup(); "
    "from django.conf import settings as s; from django.templatetags.static import static; "
    "print(json.dumps({'static': s.STATIC_URL, 'sesion': s.SESSION_COOKIE_PATH, 'csrf': s.CSRF_COOKIE_PATH, "
    "'css': static('css/app.css')}))"
)


def ajustes_con(**variables):
    """Los ajustes tal como los vería el servidor con esas variables de entorno (en un proceso aparte)."""
    entorno = (
        {k: v for k, v in os.environ.items() if k != "FORCE_SCRIPT_NAME"} | {"DEBUG": "True"} | variables
    )  # DEBUG: sin necesitar collectstatic
    r = subprocess.run(
        [sys.executable, "-c", CODIGO], cwd=RAIZ, env=entorno, capture_output=True, text=True, encoding="utf-8", check=True
    )
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_en_la_raiz_del_sitio_no_hay_prefijo():
    a = ajustes_con()
    assert a["static"] == "/static/" and a["sesion"] == "/" and a["csrf"] == "/"
    assert a["css"].startswith("/static/css/app.")


def test_dentro_de_aula_los_estilos_y_las_cookies_llevan_el_prefijo():
    # Sin el prefijo en los estilos, detrás de IIS se pedirían a la raíz del sitio y no se verían.
    a = ajustes_con(FORCE_SCRIPT_NAME="/aula")
    assert a["static"] == "/aula/static/" and a["css"].startswith("/aula/static/css/app.")
    assert a["sesion"] == "/aula/" and a["csrf"] == "/aula/"  # sus cookies no viajan al resto de la página del CETPRO
