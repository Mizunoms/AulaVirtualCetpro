"""Respaldo de la base (pg_dump) y de los archivos subidos."""

import subprocess
import zipfile
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.nucleo import respaldo
from apps.nucleo.respaldo import RespaldoError
from apps.tareas.models import Material

pytestmark = pytest.mark.django_db


def correr(*args, **opciones):
    salida = StringIO()
    call_command("respaldo", *args, stdout=salida, **opciones)
    return salida.getvalue()


@pytest.fixture
def carpeta(tmp_path):
    return tmp_path / "respaldos"


def test_respalda_la_base_con_pg_dump(carpeta, alumno):
    texto = correr(carpeta=str(carpeta))
    archivos = list(carpeta.glob("base_*.dump"))
    assert len(archivos) == 1 and "Base respaldada" in texto and "KB" in texto
    assert archivos[0].read_bytes()[:5] == b"PGDMP"  # formato «custom» de PostgreSQL
    assert not list(carpeta.glob("*.parte"))  # no queda nada a medias
    # El respaldo se puede leer y trae las tablas del aula
    pg_restore = respaldo.buscar_pg_dump().replace("pg_dump", "pg_restore")
    r = subprocess.run(
        [pg_restore, "--list", str(archivos[0])], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    assert r.returncode == 0 and "cuentas_usuario" in r.stdout and "tareas_entrega" in r.stdout


def test_con_archivos_guarda_un_zip_con_los_nombres_relativos(carpeta, settings):
    for ruta, contenido in {"2026/10/uno.pdf": b"uno", "2026/10/dos.png": b"dos", "2025/01/tres.jpg": b"tres"}.items():
        destino = settings.MEDIA_ROOT / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
    texto = correr("--archivos", carpeta=str(carpeta))
    (zip_ruta,) = carpeta.glob("archivos_*.zip")
    assert "Archivos respaldados" in texto and "3 archivos" in texto
    with zipfile.ZipFile(zip_ruta) as z:
        assert sorted(z.namelist()) == ["2025/01/tres.jpg", "2026/10/dos.png", "2026/10/uno.pdf"]
        assert z.read("2026/10/uno.pdf") == b"uno"


def test_sin_archivos_subidos_el_zip_queda_vacio_sin_fallar(carpeta, settings):
    assert not settings.MEDIA_ROOT.exists()
    correr("--archivos", carpeta=str(carpeta))
    (zip_ruta,) = carpeta.glob("archivos_*.zip")
    assert zipfile.ZipFile(zip_ruta).namelist() == []


def test_solo_se_dejan_los_respaldos_mas_recientes(carpeta):
    carpeta.mkdir()
    for dia in range(1, 21):
        (carpeta / f"base_2026-09-{dia:02d}_030000.dump").write_bytes(b"x")
        (carpeta / f"archivos_2026-09-{dia:02d}_030000.zip").write_bytes(b"x")
    (carpeta / "notas.txt").write_text("no es un respaldo")
    texto = correr(carpeta=str(carpeta), conservar=5)
    bases = sorted(p.name for p in carpeta.glob("base_*.dump"))
    zips = sorted(p.name for p in carpeta.glob("archivos_*.zip"))
    assert len(bases) == 5 and len(zips) == 5
    # Se quedan los más nuevos: el respaldo de ahora y los 4 últimos de antes
    assert bases[:4] == [f"base_2026-09-{d}_030000.dump" for d in (17, 18, 19, 20)] and bases[4] > "base_2026-10"
    assert zips == [f"archivos_2026-09-{d}_030000.zip" for d in (16, 17, 18, 19, 20)]
    assert (carpeta / "notas.txt").exists()  # lo que no es respaldo no se toca
    assert "Respaldos viejos borrados: 31" in texto  # 21 bases y 20 zips, menos los 5 + 5 que se quedan


def test_la_contrasena_no_va_en_la_linea_de_comandos(carpeta, monkeypatch, settings):
    visto = {}

    def falso_run(orden, env=None, **kw):
        visto["orden"], visto["env"] = orden, env
        archivo = next(a for a in orden if a.startswith("--file=")).split("=", 1)[1]
        open(archivo, "wb").write(b"PGDMP")
        return subprocess.CompletedProcess(orden, 0, "", "")

    monkeypatch.setattr(respaldo.subprocess, "run", falso_run)
    monkeypatch.setattr(respaldo, "buscar_pg_dump", lambda: "pg_dump")
    from django.db import connection

    monkeypatch.setitem(connection.settings_dict, "PASSWORD", "una-clave-secreta-9")
    correr(carpeta=str(carpeta))
    assert "una-clave-secreta-9" not in " ".join(visto["orden"])
    assert visto["env"]["PGPASSWORD"] == "una-clave-secreta-9"


def test_si_pg_dump_falla_no_queda_un_respaldo_a_medias(carpeta, monkeypatch):
    def falso_run(orden, **kw):
        archivo = next(a for a in orden if a.startswith("--file=")).split("=", 1)[1]
        open(archivo, "wb").write(b"a medias")
        return subprocess.CompletedProcess(orden, 1, "", "pg_dump: error: no hay conexión")

    monkeypatch.setattr(respaldo.subprocess, "run", falso_run)
    monkeypatch.setattr(respaldo, "buscar_pg_dump", lambda: "pg_dump")
    with pytest.raises(CommandError, match="pg_dump falló: pg_dump: error: no hay conexión"):
        correr(carpeta=str(carpeta))
    assert not list(carpeta.glob("base_*"))


def test_avisa_si_no_encuentra_pg_dump(monkeypatch, tmp_path):
    monkeypatch.setenv("PG_DUMP", str(tmp_path / "no-existe.exe"))
    with pytest.raises(RespaldoError, match="PG_DUMP apunta"):
        respaldo.buscar_pg_dump()
    monkeypatch.delenv("PG_DUMP")
    monkeypatch.setattr(respaldo.shutil, "which", lambda nombre: None)
    monkeypatch.setattr(respaldo.glob, "glob", lambda patron: [])
    with pytest.raises(RespaldoError, match="No encuentro «pg_dump»"):
        respaldo.buscar_pg_dump()


def test_conservar_debe_ser_positivo(carpeta):
    with pytest.raises(CommandError, match="1 o más"):
        correr(carpeta=str(carpeta), conservar=0)


def test_el_respaldo_vacia_lo_que_lleva_mas_de_30_dias_en_la_papelera(carpeta, clase):
    viejo = Material.objects.create(clase=clase, titulo="Viejo", tipo="enlace", url="https://x.pe")
    reciente = Material.objects.create(clase=clase, titulo="Reciente", tipo="enlace", url="https://x.pe")
    Material.todos.filter(pk=viejo.pk).update(eliminado=timezone.now() - timedelta(days=40))
    Material.todos.filter(pk=reciente.pk).update(eliminado=timezone.now() - timedelta(days=3))
    texto = correr(carpeta=str(carpeta))
    assert not Material.todos.filter(pk=viejo.pk).exists() and Material.todos.filter(pk=reciente.pk).exists()
    assert "Papelera: 1 elementos de más de 30 días borrados." in texto
