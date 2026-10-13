# Prototipo

Prototipo interactivo (celular y PC, docente y alumno, con asistente IA simulado):

https://claude.ai/artifact/V2uwjVXBD8tZ6Vc7DTVLvW

> Es privado: para mostrarlo a otros, compártelo desde el menú **Compartir** del prototipo.
> Los datos (alumnos, notas) son de ejemplo. Sirve como guía visual para las vistas de `src/app/views/`.

## Pantallas
Celular y PC tienen las mismas pantallas (menú de abajo en celular, menú lateral en PC).
Estructura explicada en [08 - Análisis de Blackboard](08-analisis-blackboard.md).

| Rol | Menú | Pantallas |
|---|---|---|
| Docente | Inicio · Mis cursos · Por calificar · Mi cuenta | Inicio (clase de hoy, por calificar, próximas fechas), curso, clases y materiales, tareas, nueva tarea, trabajos entregados, calificar, asistencia, notas y reportes |
| Alumno | Inicio · Mis cursos · Mis notas · Mi cuenta | Inicio (tareas por entregar y avisos), curso, clases y materiales, tareas, entregar tarea (2 pasos), mis notas, mi asistencia |
| Ambos | | Mi cuenta (letra grande, alto contraste, voz, salir) · Asistente IA (panel desde abajo en celular, panel lateral en PC) |

## Identidad visual (igual que la página web del CETPRO)
Tomada de la web pública del CETPRO (repositorio `Pagina-web`, `assets/css/style.css`) para que el aula se
sienta parte del mismo instituto.

- **Logo:** `src/public/img/logo-cetpro.png` (engranaje rojo con Machu Picchu). Va en el encabezado.
- **Encabezado:** fondo azul marino `#0B1B35`, línea roja de 3 px abajo `#C8231B`, logo + "CETPRO MANGOMARCA".
- **Colores**

  | Uso | Color | Contraste |
  |---|---|---|
  | Encabezado, texto principal | Azul marino `#0B1B35` | 15.3 sobre el fondo |
  | Botones principales, enlaces | Azul `#1249A3` (hover `#0D3882`) | 8.4 con texto blanco |
  | Acento: asistente, avisos | Rojo `#C8231B` | 5.7 con texto blanco |
  | Fondo de página | `#EEF2F9` · tarjetas `#FFFFFF` | — |
  | Texto secundario | `#55627F` | 5.4 sobre el fondo |
  | Detalle decorativo | Dorado `#E8A020` | **solo** sobre azul marino, nunca texto sobre blanco |

  El gris de la web (`#6B7A99`) se oscureció a `#55627F` porque no llegaba a 4.5:1.
- **Estados:** entregó `#166534` sobre `#DCFCE7` · tardía `#92400E` sobre `#FEF3C7` · falta `#991B1B` sobre `#FEE2E2`
- **Letras (Google Fonts):** **Nunito** para todo el texto; **Barlow Condensed** solo para el nombre
  "CETPRO MANGOMARCA" y los títulos grandes de página. No usar mayúsculas en textos largos ni en botones.
- **No se copia** de la web el carrusel, las animaciones ni las sombras fuertes: el aula es para trabajar.

## Fácil de usar (personas mayores y con poca práctica en computadora)
- Botones con **texto visible** ("Volver", "Entregar tarea"), no solo íconos. El ícono acompaña al texto.
- **Una acción principal por pantalla**, en un botón grande (mín. 48 px de alto) y del color principal.
- Letra base **16 px** o más; menú inferior del celular con letra de 16 px.
- Pocas opciones en el menú (celular: 2 a 4). Siempre se ve en qué pantalla estás.
- Frases cortas y palabras de todos los días ("Mis notas", no "Calificaciones").
- Confirmar con un mensaje claro y verde cuando algo se guardó o se entregó.
- Botón para agrandar la letra y el asistente (escrito o voz) siempre a la mano.
