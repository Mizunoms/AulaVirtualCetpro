# Decisiones de arquitectura

Fecha: 13 de octubre de 2026. Cambia una decisión → se actualiza este documento.

## Por qué se rehace
El sistema en PHP sirvió para el piloto y está guardado completo (etiqueta `php-prueba-2026-10-13`). Para crecer
(API para app móvil y asistente IA, tareas en segundo plano, más módulos) conviene una base más moderna, con
muchas librerías listas (`pip`) y un framework que ya trae usuarios, permisos, migraciones y panel técnico.

## Decisiones

| Tema | Decisión | Motivo |
| ---- | -------- | ------ |
| Lenguaje | Python 3.12 | Muchas librerías (Excel, PDF, IA, datos), fácil de mantener |
| Framework | Django 5.2 LTS | Trae autenticación, ORM, migraciones, CSRF, admin; soporte hasta abril de 2028 |
| Base de datos | PostgreSQL 18 | Robusta, buen manejo de texto/fechas/JSON, reemplaza a MariaDB |
| Forma | Monolito modular (apps) | Un solo programa que desplegar; cada app es un módulo con su responsabilidad |
| Pantallas | Plantillas de Django (HTML en el servidor) | Rápidas en celulares viejos, accesibles, sin build de JavaScript |
| Interactividad | JavaScript simple; HTMX si hace falta | Evitar un frontend aparte mientras no sea necesario |
| API | Más adelante, con Django Ninja o DRF | Para app móvil / integraciones; sin duplicar reglas |
| Tareas en segundo plano | Django-Q2 o Huey (usan PostgreSQL) | Celery/Redis no se llevan bien con Windows |
| Tiempo real | Django Channels solo si se necesita | No hay requisito hoy |
| Servidor | Windows Server + IIS por delante + Waitress como servicio | El servidor del CETPRO sigue siendo Windows |
| Otros lenguajes | Solo por uso justificado (ej. Node/TypeScript para una PWA o tiempo real) | Cada lenguaje extra es algo más que mantener |

## Compatibilidad con el sistema anterior
- Mismos textos, reglas y nombres de pantalla (curso / módulo / unidad didáctica / clase).
- Mismas direcciones (URL) donde se pueda: así las ~700 comprobaciones del sistema PHP (`tests/` del repositorio
  viejo, con cliente HTTP en Python) sirven como **pruebas de aceptación** de este.
- El sistema nuevo empieza desde cero: no se traen datos del piloto (la base anterior queda guardada aparte).

## Seguridad y datos
- Claves y configuración solo en `.env` (no se sube a Git).
- Datos del alumno: solo DNI, nombres, apellidos, celular, correo (opcional) y fecha de nacimiento.
- Archivos subidos fuera de `static/`, servidos por una vista con permisos.
- Al IA nunca se le envían DNI, contraseñas ni datos de discapacidad.
