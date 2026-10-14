# CLAUDE.md — Aula Virtual CETPRO Mangomarca (versión nueva: Python + Django)

Contexto para Claude Code. Léelo antes de cualquier cambio.

## Qué es
Aula virtual tipo Blackboard para el CETPRO Mangomarca (centro de educación técnico-productiva público en
San Juan de Lurigancho, Lima). Docentes publican materiales, dejan tareas, califican y toman asistencia;
alumnos entregan trabajos (muchas veces con foto desde el celular) y ven sus notas.

Usuarios: docentes de cursos prácticos, alumnos que incluyen **personas adultas** y **personas con
discapacidad**. Muchos encuentran "complicadas" las plataformas: **la simplicidad y la accesibilidad son
requisitos, no extras.**

Este repositorio es la **versión nueva**. La versión anterior (PHP, usada en el piloto) está guardada en
`AulaVirtualCetproMangomarca` (rama `feature/version-2`, etiqueta `php-prueba-2026-10-13`). Se rehace aquí con
las mismas pantallas, textos y reglas. El sistema nuevo empieza desde cero: no se traen datos del piloto.

## Documentación
- `docs/00-decisiones.md` — por qué este stack y cómo se organiza
- `docs/01-plan.md` — fases y checklist (marcar al terminar)
- `docs/02-servidor-windows.md` — instalar en el servidor del CETPRO (IIS + Waitress + PostgreSQL) y respaldos
- `docs/heredados/` — documentos del sistema anterior que siguen valiendo: visión, requerimientos (RF/RNF),
  análisis de Blackboard, asistente IA, prototipo/colores, entrevistas, y el esquema SQL de la base vieja
  (`schema-php.sql`, solo como referencia).

Si un cambio contradice estos documentos, avisa antes de hacerlo. Si cambia una decisión, actualiza el doc.

## Stack
- Python 3.12 · Django 5.2 LTS · PostgreSQL 18 · `psycopg` 3
- Plantillas de Django en el servidor (HTML), CSS propio con variables, JavaScript simple (HTMX si hace falta)
- Configuración por variables de entorno (`.env`, con `django-environ`); `.env` NO se sube a Git
- Producción: Windows Server + IIS por delante → Waitress (servicio de Windows) → Django. WhiteNoise para css/js
- Pruebas: `pytest` + `pytest-django` · Estilo: `ruff`
- Un solo proyecto, organizado en apps (monolito modular). Otros lenguajes solo si un caso lo justifica (ver decisiones)

## Estructura
```
config/            settings, urls, wsgi
apps/cuentas/      usuarios, entrar/salir, preferencias de accesibilidad
apps/nucleo/       configuración del CETPRO (ajuste()), registro de actividad, páginas comunes
apps/academico/    cursos, módulos, unidades didácticas, clases, matrículas, tareas, notas, asistencia…
templates/         base.html y plantillas por app (templates/<app>/…)
static/            css, js, img
storage/uploads    archivos subidos — fuera de static, se sirven con un controlador con permisos
scripts/           utilidades (crear base PostgreSQL)
tests/
```

## Palabras (igual que en el sistema anterior)
- **Curso** = programa de estudios (la especialidad, ej. Soporte Técnico).
- **Módulo** = Módulo 1 o 2 de un curso, con su docente, turno y alumnos.
- **Unidad didáctica** = lista informativa del módulo (nombre, créditos y horas).
- **Clase** = lo que el docente abre con fechas de apertura y cierre.
- Alumnos entran con DNI y contraseña; docentes y administración con correo (si escriben solo «maria», se completa `@cetpro.com`).

## Reglas de código
- PEP 8 con `ruff` (línea de 110). Clases `PascalCase`, funciones y variables `snake_case`.
  Nombres de dominio en español (`Modulo`, `matricula`), igual que en pantalla.
- Tablas con el nombre de la app (`academico_modulo`…). Las migraciones se crean con `makemigrations` y se suben a Git.
- **Seguridad siempre**: ORM de Django (nunca SQL armado con texto), plantillas con autoescape (nunca `|safe` con datos de
  personas), `{% csrf_token %}` en todo formulario POST, contraseñas con el hasher de Django, validar extensión + tipo
  de archivo y renombrar lo que se sube, limitar intentos de entrada.
- Verificar rol y pertenencia al curso en cada vista (un alumno nunca ve datos de otro). Preferir decoradores/mixins
  comunes en `apps/nucleo/permisos.py` en vez de repetir comprobaciones.
- Colores, logo, textos y especialidades se leen de la configuración del CETPRO (`ajuste()`), no se escriben fijos.
- Notas en escala 0–20 (`DecimalField(max_digits=4, decimal_places=2)`).
- Del alumno solo se guarda lo necesario: DNI, nombres, apellidos, celular, correo (opcional) y fecha de nacimiento.
- Textos de la interfaz en **español simple**, frases cortas.

## Reglas de interfaz
- **Mobile-first** y también PC: en celular menú inferior y una columna; en PC menú lateral y tablas completas.
- Accesibilidad WCAG 2.1 AA: botones ≥ 44 px, contraste 4.5:1, `<label>` en todos los campos, elementos reales
  (`<button>`, `<a>`), `aria-label` en botones de solo ícono, usable con TalkBack y teclado.
- Respetar las preferencias de la persona (tamaño de letra, alto contraste, voz).
- **«Eliminar» borra de verdad**; «Desactivar» o «Archivar» son botones aparte (nunca un «Eliminar» que en realidad
  desactiva). Todo «Eliminar» pasa por una pantalla que dice qué se pierde y, si hay trabajos, notas o mensajes, pide
  marcar «Entiendo»; se borran también los archivos subidos y queda anotado en el registro de actividad.
  Los trabajos, notas y asistencia de los alumnos son del CETPRO: el docente solo elimina su módulo si todavía no los
  tiene; si ya los tiene (o está archivado), lo elimina el administrador. Vale para todos los CRUD.
- Modo claro/oscuro (cookie `aula_tema`, atributo `data-tema` en `<html>`): en el CSS usar las variables
  (`var(--superficie)`, `var(--texto)`, `var(--borde)`…), no colores fijos como `#fff`.
- El sistema debe funcionar completo **sin** el asistente IA.
- Diseño limpio y simple; no agregar adornos ni rediseñar pantallas que no se pidieron.

## Asistente IA (más adelante)
- La clave de API vive solo en `.env` del servidor. Nunca en JS.
- El modelo solo pide acciones de una lista cerrada (ver `docs/heredados/07-asistente-ia.md`); el servidor las ejecuta con
  los permisos del usuario. Nada se guarda, publica, califica ni envía sin confirmación.
- No enviar al modelo DNI, contraseñas ni datos de discapacidad.

## Forma de trabajar
- Cambios pequeños y enfocados; no tocar lo que no tiene que ver con la tarea.
- Seguir la fase actual de `docs/01-plan.md` y marcar los checks al terminar.
- Commits: `tipo: descripción en español` (`feat`, `fix`, `docs`, `style`, `refactor`, `db`, `test`, `chore`).
- Ramas: `main` (producción), `develop`, `feature/<nombre>`, `fix/<nombre>`.
- **No subir nada a GitHub sin que el usuario lo pida** (commits locales sí).
- Cada función nueva lleva su prueba en `tests/`. Las pruebas usan una base temporal (`test_…`) que Django crea y borra
  sola; **nunca** apuntan a la base real ni borran archivos reales.
- Borrar contenido del docente = papelera (`eliminado_at`); toda consulta sobre tareas, formularios o materiales filtra
  los eliminados.
- Una vista nunca recibe una variable de contexto llamada `usuario` para otra persona: `user` es la persona conectada.

## Comandos (en Windows, desde la carpeta del proyecto)
```
.venv\Scripts\python manage.py runserver        # servidor local → http://127.0.0.1:8000
.venv\Scripts\python manage.py makemigrations   # crear migraciones tras cambiar modelos
.venv\Scripts\python manage.py migrate          # aplicarlas a la base
.venv\Scripts\python -m pytest                  # pruebas
.venv\Scripts\ruff check . ; .venv\Scripts\ruff format .
powershell -ExecutionPolicy Bypass -File scripts\crear-base-postgres.ps1   # primera vez: crea la base y .env
.venv\Scripts\python aceptacion\correr.py     # pruebas de aceptación: guiones HTTP del sistema anterior (base propia, puerto 8090)
.venv\Scripts\python manage.py respaldo [--archivos]   # respaldo de la base (y de los archivos subidos)
```
