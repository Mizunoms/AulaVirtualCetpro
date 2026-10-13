# 02 - Requerimientos

> Actualizada con las 3 primeras entrevistas (ver [resumen](entrevistas/resumen.md)). Se seguirá ajustando.
> Prioridad: **Alta** = versión 1, **Media** = si alcanza el tiempo, **Baja** = versiones futuras.

## Requerimientos funcionales

### Autenticación y usuarios
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-01 | Iniciar sesión con correo (o DNI) y contraseña | Alta |
| RF-02 | Control de acceso por rol (admin, dirección, docente, alumno) | Alta |
| RF-03 | Recuperar / cambiar contraseña | Media |
| RF-04 | Editar perfil (foto, teléfono, correo) | Baja |

### Cursos
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-05 | Crear cursos por periodo, especialidad, módulo y turno | Alta |
| RF-06 | Asignar docente(s) y matricular alumnos en un curso | Alta |
| RF-07 | Organizar el contenido del curso por semanas o unidades | Alta |

### Materiales
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-08 | Subir archivos (PDF, Word, PPT, imágenes) | Alta |
| RF-09 | Publicar enlaces y videos (YouTube) | Alta |
| RF-10 | Ocultar / mostrar material por fecha | Media |

### Tareas y entregas
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-11 | Crear tarea con descripción, archivo adjunto, fecha límite y puntaje | Alta |
| RF-12 | Definir si la tarea es individual o grupal | Alta |
| RF-13 | El alumno entrega archivo, foto (desde la cámara del celular) o enlace | Alta |
| RF-14 | Por tarea: no aceptar, aceptar o aceptar con penalidad las entregas tardías | Alta |
| RF-15 | El docente califica y deja comentario en cada entrega | Alta |
| RF-16 | Ver lista de quién entregó y quién no | Alta |
| RF-28 | Por tarea, elegir forma de calificar: nota 0–20, rúbrica o aprobado/desaprobado | Alta |
| RF-29 | Botón "Compartir en WhatsApp" con el enlace de la tarea o anuncio | Alta |

### Cuestionarios
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-17 | Formularios como Google Forms: examen (puntos y nota automática 0–20), trabajo (nota del docente) o encuesta (sin nota). Tipos: varias opciones, casillas, lista desplegable, verdadero/falso, respuesta corta, párrafo, escala lineal, fecha, hora, subir archivo/foto, cuadrículas y títulos de sección; preguntas obligatorias, opción «Otra», imagen en la pregunta, duplicar, vista previa, resumen de respuestas con gráficos y descarga para Excel | Alta |
| RF-18 | Límite de tiempo, número de intentos (vale la mejor nota), mezclar preguntas y mostrar respuestas al terminar | Alta |

### Asistencia
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-19 | Registrar asistencia por sesión (presente, tarde, falta, justificada) | Alta |
| RF-20 | Ver porcentaje de asistencia por alumno | Alta |

### Calificaciones y reportes
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-21 | Libro de notas del curso con promedio por alumno | Alta |
| RF-22 | El alumno ve sus notas y comentarios | Alta |
| RF-23 | Exportar notas y asistencia a Excel / PDF con el formato oficial de dirección | Alta |
| RF-24 | Panel para dirección con gráficos (Chart.js) | Media |

### Comunicación
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-25 | Anuncios del docente para todo el curso | Alta |
| RF-26 | Notificaciones dentro del sistema (nueva tarea, tarea calificada) | Media |
| RF-27 | Notificaciones por correo | Baja |

### Asistente virtual con IA (ver [07 - Asistente IA](07-asistente-ia.md))
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-30 | Botón de asistente visible en todas las pantallas | Alta |
| RF-31 | Dos modos de uso: escrito y voz (dictado + respuesta leída en voz alta), elegible por usuario | Alta |
| RF-32 | El asistente abre pantallas y guía paso a paso según el rol (docente / alumno) | Alta |
| RF-33 | El asistente llena borradores (ej. tarea) y pide confirmación antes de guardar | Media |
| RF-34 | El asistente cambia la configuración de accesibilidad (letra, contraste, voz) | Alta |
| RF-35 | El asistente lee en voz alta el contenido de la pantalla | Alta |
| RF-36 | El asistente responde dudas de uso con el manual del sistema | Alta |

### Accesibilidad
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-37 | Ajustar tamaño de letra y modo alto contraste, guardados por usuario | Alta |
| RF-38 | Leer en voz alta materiales, anuncios e instrucciones de tareas | Alta |

### Navegación estándar (ver [08 - Análisis de Blackboard](08-analisis-blackboard.md))
| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-39 | Menú de 4 opciones igual en todo el sistema. Alumno: Inicio, Mis cursos, Mis notas, Mi cuenta. Docente: Inicio, Mis cursos, Por calificar, Mi cuenta | Alta |
| RF-40 | Inicio del alumno: tareas por entregar agrupadas en "Ya pasó la fecha", "Vence hoy" y "Próximas", con botón "Entregar", y avisos de sus profesores | Alta |
| RF-41 | Inicio del docente: clase de hoy con botón "Tomar asistencia", cantidad de trabajos por calificar y próximas fechas | Alta |
| RF-42 | "Por calificar": lista de todos los trabajos sin nota del docente; al guardar una nota se abre el siguiente | Alta |
| RF-43 | Todos los cursos tienen las mismas secciones: avisos, clases y materiales por semana, tareas, notas y asistencia | Alta |
| RF-44 | "Mi cuenta": letra grande, alto contraste, leer en voz alta, cambiar contraseña, enlace a la web del CETPRO y cerrar sesión | Alta |
| RF-45 | Número rojo en el menú cuando hay pendientes (tareas por entregar / trabajos por calificar) | Media |
| RF-46 | Secciones especiales por especialidad (según encuestas), sin cambiar las secciones estándar | Baja |
| RF-47 | Mensajería privada alumno ↔ docente dentro de cada curso, con aviso de mensajes nuevos | Alta |
| RF-49 | Importar preguntas a un formulario pegando el texto de una IA (ChatGPT, Gemini…) o subiendo Excel, CSV o Word; vista previa con errores y confirmación antes de guardar; plantilla de Excel e instrucción lista para copiar a la IA | Alta |
| RF-48 | ~~Modo prueba: entrar solo con el nombre~~ — usado en la prueba del 07/10/2026 y retirado en la versión 2 | — |
| RF-50 | El alumno crea su cuenta con su DNI: con el código del módulo que le da su profesor, o confirmando sus datos si el CETPRO lo cargó en una lista; recibe una contraseña temporal y enseguida elige una propia que recuerde | Alta |
| RF-51 | El admin carga listas de alumnos desde Excel/CSV o pegadas (DNI, nombres, apellidos, celular, fecha de nacimiento, código del módulo) | Alta |
| RF-52 | El docente crea sus módulos; cada módulo tiene un código de inscripción que se puede cambiar y cerrar | Alta |
| RF-53 | Clases con fecha de inicio y fin que se abren y cierran solas; el docente puede abrirlas o cerrarlas a mano; en una clase cerrada no se entregan tareas ni tests | Alta |
| RF-54 | El alumno solo ve los módulos en los que está inscrito; puede unirse a otro con su código | Alta |
| RF-55 | Panel Admin → Ajustes: nombres, colores (con control de contraste), logo, foto de entrada, frase de bienvenida, WhatsApp/teléfono de ayuda, aviso para todos, periodo, registro abierto y especialidades con su color | Alta |
| RF-56 | El docente (para sus alumnos) y el admin (para todos) pueden dar una contraseña nueva que se muestra una sola vez | Alta |
| RF-57 | Papelera: lo borrado se recupera durante 30 días | Alta |
| RF-58 | Nota final del módulo con pesos que elige el docente (trabajos, tests, asistencia) y nota para aprobar | Alta |
| RF-59 | Avisos dentro del aula (campana) y recordatorio por WhatsApp a quienes no entregaron | Alta |
| RF-60 | El docente puede devolver un archivo o foto al calificar | Media |
| RF-61 | Copiar un módulo al siguiente periodo con sus clases, materiales, tareas y formularios | Media |
| RF-62 | Preguntas de la clase: los alumnos preguntan y el docente responde | Media |
| RF-63 | «Eliminar» borra de verdad: el administrador elimina cuentas (una o varias) y módulos, y el docente sus módulos mientras no tengan trabajos, tests ni asistencia de alumnos, siempre tras una pantalla que dice qué se pierde (y una casilla «Entiendo» si hay trabajos, notas o mensajes). «Desactivar» y «Archivar» son botones aparte. No se elimina a uno mismo ni a un docente con módulos a su cargo | Alta |
| RF-64 | El administrador ve **Cursos** (programas de estudios) con sus módulos adentro y crea los módulos dentro de un curso; el docente también puede crear sus módulos eligiendo el curso. Cada módulo puede tener unidades didácticas (nombre, créditos y horas, como en el plan de estudios) | Alta |
| RF-65 | El administrador y el docente pueden **cargar el plan de estudios** (el Excel del Ministerio, hoja «Organización modular»): el aula lee el curso, sus módulos y las unidades didácticas con créditos y horas, muestra lo que encontró y, con la confirmación de la persona, crea los módulos o completa los que ya existen | Alta |
| RF-66 | Cargar alumnos desde el Excel de la inscripción (apellido paterno y materno, nombres, DNI, teléfono, fecha de nacimiento y módulo); solo se guarda lo necesario. Cada alumno puede inscribirse en uno o en los dos módulos (casillas o columna «Módulo»: 1, 2, «1 y 2» o código) | Alta |
| RF-67 | Enviar a cada alumno su DNI y una contraseña temporal por WhatsApp (al cargar la lista, o para todo un módulo); la cambia al entrar. El envío por correo queda para cuando el CETPRO tenga su correo institucional | Alta |
| RNF-SEG | Respaldo diario automático; actualizaciones de base con registro; cookie segura y CSP | Alta |

## Requerimientos no funcionales

| ID | Requerimiento |
|---|---|
| RNF-01 | **Responsive:** usable en celulares de gama baja y pantallas pequeñas |
| RNF-02 | **Seguridad:** contraseñas con `password_hash`, consultas preparadas (PDO), protección CSRF y XSS, validación de archivos subidos |
| RNF-03 | **Archivos:** límite de 10 MB por archivo; solo extensiones permitidas; guardados fuera de la carpeta pública |
| RNF-04 | **Rendimiento:** páginas principales cargan en menos de 3 s con conexión móvil |
| RNF-05 | **Usabilidad:** interfaz simple, en español, pensada para usuarios con poca experiencia en plataformas |
| RNF-06 | **Respaldo:** copia de la base de datos y archivos al menos una vez por semana |
| RNF-07 | **Compatibilidad:** Chrome, Edge y Firefox recientes; Chrome en Android |
| RNF-08 | **Celular y PC:** el mismo sistema web funciona completo en celular (prioridad, porque docentes y alumnos lo usan más así) y en PC. En celular: menú inferior y pantallas en una columna. En PC: menú lateral, tablas completas y asistente como panel lateral |
| RNF-09 | **Simplicidad:** las tareas frecuentes (dejar tarea, calificar, tomar asistencia) en pocos toques; los docentes encuentran "complicadas" las plataformas actuales |
| RNF-10 | **Capacitación:** sesión práctica para docentes y videos cortos por función |
| RNF-11 | **Accesibilidad WCAG 2.1 AA:** usable con lector de pantalla (TalkBack) y teclado, contraste mínimo 4.5:1, botones de al menos 44 px, etiquetas en todos los campos. El sistema funciona completo aunque el asistente IA no esté disponible |
| RNF-12 | **Lenguaje simple:** textos cortos y claros, pensados para personas adultas y con poca experiencia digital |
| RNF-13 | **Privacidad IA:** al modelo no se envían DNI, contraseñas ni datos de discapacidad; la clave de API solo en el servidor |

## Historias de usuario (ejemplos)

- Como **docente**, quiero dejar una tarea con fecha límite para que todos los alumnos la vean en un solo lugar.
- Como **docente**, quiero ver quién no entregó para recordarles antes del cierre.
- Como **alumno**, quiero subir una foto de mi trabajo desde el celular para no necesitar computadora.
- Como **alumno**, quiero ver mis notas y comentarios para saber en qué mejorar.
- Como **dirección**, quiero un reporte de asistencia por curso para el seguimiento mensual.

## Pendiente de validar en entrevistas

- [x] ¿Escala de notas única o también rúbricas? → Se usan 0–20, rúbrica y aprobado/desaprobado (RF-28)
- [x] ¿Las tareas grupales son frecuentes? → 2 de 3 docentes las usan (RF-12 sube a Alta)
- [ ] ¿Qué formato de reporte pide dirección? → Excel cada 3 meses / fin de módulo; falta conseguir el formato
- [ ] ¿Mensajería interna o WhatsApp? → Opiniones divididas; por ahora se integra con WhatsApp (RF-29)
- [x] ¿Cuestionarios en línea tienen demanda? → Las 3 toman exámenes (RF-17 sube a Alta)
- [ ] ¿Cuál es la nota mínima aprobatoria? → El prototipo usa 11; confirmar con dirección
- [ ] ¿Qué secciones especiales necesita cada especialidad? → Encuestas (RF-46)
