# Aula Virtual CETPRO Mangomarca

Aula virtual para el CETPRO Mangomarca (San Juan de Lurigancho, Lima): docentes publican materiales,
dejan tareas, califican y toman asistencia; alumnos entregan trabajos desde el celular y ven sus notas.

Versión nueva en **Python + Django + PostgreSQL**. La versión anterior (PHP, usada en el piloto) vive en el
repositorio `AulaVirtualCetproMangomarca`.

## Primera vez en tu PC (Windows)

Requisitos: Python 3.12 y PostgreSQL 18 instalados.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
powershell -ExecutionPolicy Bypass -File scripts\crear-base-postgres.ps1   # crea la base y el archivo .env
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
```

Abrir <http://127.0.0.1:8000> y entrar con el correo y la contraseña del superusuario
(en «Soy profesor» se puede escribir solo la parte antes de la `@`).

Para probar con cuentas de ejemplo (solo en tu PC): `.venv\Scripts\python manage.py datos_demo`
(crea un administrador, un docente y un alumno; las claves están en el propio comando).

## Pruebas

```powershell
.venv\Scripts\python -m pytest
```

Las pruebas crean y borran una base temporal (`test_aula_virtual_cetpro`); no tocan los datos reales.

## Documentación

- [CLAUDE.md](CLAUDE.md) — reglas del proyecto
- [docs/00-decisiones.md](docs/00-decisiones.md) — por qué este stack
- [docs/01-plan.md](docs/01-plan.md) — fases y avance
- [docs/heredados/](docs/heredados) — visión, requerimientos y análisis del sistema anterior
