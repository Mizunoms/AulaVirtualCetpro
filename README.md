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

### Pruebas de aceptación (las del sistema anterior)

Los guiones HTTP del sistema PHP están copiados en `aceptacion/guiones/` y se corren contra este sistema:

```powershell
.venv\Scripts\python aceptacion\correr.py                  # los cuatro guiones
.venv\Scripts\python aceptacion\correr.py test_version2    # solo uno
```

Cada guion arma una base propia (`aula_virtual_aceptacion`, nunca la de trabajo), carga los mismos datos de prueba
que el sistema anterior (`manage.py datos_aceptacion`), levanta el sitio con Waitress en el puerto 8090 y guarda el
resultado en `aceptacion/.tmp/salida-<guion>.txt`. Si una comprobación falla, la última pantalla queda en
`aceptacion/.tmp/fallas/`. Hoy pasan las 536 comprobaciones.

Diferencias a propósito (marcadas con `DIFERENCIA A PROPÓSITO` en los guiones):
- Al darle una contraseña nueva a alguien, Django cierra sus sesiones abiertas (más seguro que antes).
- No existen las cuentas del antiguo «modo prueba» (el sistema nuevo empieza sin datos del piloto).
- Los archivos subidos están en la carpeta temporal de la prueba, y el Excel no pone comillas a los textos con espacios.

## Documentación

- [CLAUDE.md](CLAUDE.md) — reglas del proyecto
- [docs/00-decisiones.md](docs/00-decisiones.md) — por qué este stack
- [docs/01-plan.md](docs/01-plan.md) — fases y avance
- [docs/02-servidor-windows.md](docs/02-servidor-windows.md) — instalar en el servidor del CETPRO (IIS + Waitress + PostgreSQL) y respaldos
- [docs/03-puesta-en-marcha.md](docs/03-puesta-en-marcha.md) — dejar el aula lista, probarla con un profesor y un celular, y abrirla a todos
- [docs/heredados/](docs/heredados) — visión, requerimientos y análisis del sistema anterior
