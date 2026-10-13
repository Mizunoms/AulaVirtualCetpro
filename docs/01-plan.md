# Plan de desarrollo

Marcar `[x]` al terminar. Cada función lleva su prueba en `tests/`.

## Fase 0 — Base del proyecto
- [x] Repositorio nuevo, entorno virtual, Django 5.2, dependencias
- [x] Usuario propio (DNI o correo), entrar y salir, panel técnico de Django
- [x] Plantilla base accesible y primeras pruebas
- [x] Base PostgreSQL creada (`scripts/crear-base-postgres.ps1`) y `migrate` corrido
- [x] Pruebas corriendo contra PostgreSQL 18 y pantalla de entrar vista en el navegador
- [x] Primer commit

## Fase 1 — Núcleo (mismas pantallas, textos y direcciones que el sistema PHP)
- [x] Marco general igual al anterior (CSS, JS, logo y colores copiados): menú inferior en celular, lateral en PC
- [x] Entrar: «Soy alumno» (DNI) / «Soy profesor» (correo o solo el nombre), cuenta pendiente → «Crear mi cuenta»
- [x] Límite de intentos al entrar (por cuenta y por red)
- [x] Mi cuenta: tamaño de letra, alto contraste, voz, modo claro/oscuro, cambiar contraseña
- [x] Contraseña temporal: obliga a elegir una propia (`/cuenta/nueva-clave`)
- [x] Ajustes del aula (administrador): identidad y colores (con control de contraste), periodo, contacto, logo y foto de entrada, fotos de talleres
- [x] Permisos por rol (`@exigir`), registro de actividad (`/admin/registro`), páginas de error con el marco del aula
- [x] Subida segura de archivos (extensión + tipo real, nombre al azar, fuera de `static/`)
- [ ] Pestaña «Cursos» (especialidades) de Ajustes — se hace con los módulos, en la fase 2

## Fase 2 — Académico
- [x] Cursos (programas) y módulos del administrador: catálogo con filtros, crear, editar, archivar, **eliminar de verdad**
- [x] Unidades didácticas (nombre, créditos, horas) y pestaña «Cursos» de Ajustes (renombrar en cascada)
- [x] Clases con fechas de apertura y cierre (se abren y cierran solas, o a mano), crear varias de una vez, mover, borrar
- [x] Matrículas (1 o 2 módulos por alumno): lista pegada, código de inscripción, «Preparar accesos» por WhatsApp
- [x] «Crear mi cuenta» (DNI + código del módulo, o DNI cargado en lista) con contraseña temporal
- [x] Inicio del alumno, del docente, de administración y de dirección; «Mis módulos»; página del módulo y de la clase
- [x] Avisos del módulo, preguntas de la clase y campana de notificaciones
- [x] Contenido de las clases (materiales, tareas, formularios) conectado por `apps/academico/contenido.py` — lo llenan las fases 3 y 4

## Fase 3 — Contenido y trabajos
- [x] Materiales (archivo, enlace, video de YouTube) con papelera de 30 días y recuperar
- [x] Tareas con criterios (suman 20), política de entrega tarde (no acepta / acepta / resta puntos) y archivo adjunto
- [x] Entregas con foto desde el celular, archivo o enlace; reenviar mientras no tenga nota
- [x] Calificar (nota, rúbrica, aprobó/no aprobó), comentario, archivo devuelto, «Guardar y ver el siguiente»
- [x] Bandeja «Por calificar» con filtros y «Calificados recientemente»
- [x] Archivos servidos solo con permisos (dueño, docente del módulo, administración); se borran al eliminar lo que los tenía
- [x] Copiar el módulo para el siguiente periodo y papelera del módulo

## Fase 4 — Evaluación y comunicación
- [ ] Formularios con nota (editor, responder con tiempo, resultados, importar Excel)
- [x] Asistencia (tomar lista del día, historial, % por alumno)
- [x] Notas y evaluación del módulo (pesos 50/30/20, nota mínima 11), «Mis notas», Excel e impresión, consolidado
- [x] Preguntas de la clase y notificaciones
- [x] Mensajes alumno ↔ docente (con foto o archivo, «mensaje a todos», solo los dos participantes ven el archivo)

## Fase 5 — Panel del CETPRO
- [ ] Personas (crear, editar, «Más», desactivar y **eliminar de verdad**)
- [ ] Importar plan de estudios (Excel) y alumnos (Excel de Google Forms)
- [ ] Claves temporales y envío por WhatsApp
- [ ] Respaldo desde el panel

## Fase 6 — Asistente IA y API
- [ ] API REST con permisos por rol
- [ ] Asistente IA (escrito y voz) con lista cerrada de acciones y confirmación

## Fase 7 — Datos del piloto y servidor
- [ ] Script de migración MariaDB → PostgreSQL (`scripts/migrar_desde_php.py`)
- [ ] Pruebas de aceptación con el cliente HTTP del sistema anterior
- [ ] Servidor Windows: Waitress como servicio + IIS (reverse proxy), guía en `docs/`
