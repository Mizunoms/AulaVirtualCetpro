# 07 - Asistente virtual con IA

## Por qué

En el CETPRO estudian **personas adultas** y **personas con discapacidad**, y en las entrevistas los docentes
dijeron que las plataformas les parecen "complicadas". El asistente ayuda a cualquier usuario a hacer las cosas
hablando o escribiendo en lenguaje normal, sin tener que saber dónde está cada botón.

> El asistente es una **ayuda extra, no reemplaza** la accesibilidad básica. Todo el sistema debe poder usarse
> sin IA (lector de pantalla, teclado, letra grande), porque la IA puede fallar o no tener internet.

## Qué hace

### Para el alumno
| Pedido | Qué hace el asistente |
|---|---|
| "¿Qué tengo pendiente?" | Lista sus tareas con fecha límite |
| "Ayúdame a entregar mi tarea" | Abre la tarea y lo guía paso a paso (tomar foto → enviar) |
| "¿Cuál es mi nota?" | Muestra promedio y notas con comentarios |
| "Letra más grande" / "Alto contraste" | Cambia la configuración de accesibilidad |
| "Léeme la pantalla" | Lee en voz alta el contenido |
| "¿Qué dijo la profesora?" | Lee los últimos anuncios |

### Para el docente
| Pedido | Qué hace el asistente |
|---|---|
| "Toma asistencia de hoy" | Abre la asistencia del curso con todos en "Presente" |
| "Crea una tarea para el viernes sobre…" | Llena un borrador de tarea; el docente revisa y confirma |
| "¿Quién no entregó?" | Lista los que faltan y ofrece recordatorio por WhatsApp |
| "Reporte para dirección" | Abre las notas y genera el Excel |
| "¿Cómo subo un video?" | Explica usando el manual del sistema |

## Modos: escrito y voz

El asistente tiene **dos formas de uso**, y el usuario elige la que le acomode (se guarda en `av_preferencias`):

| | Modo escrito | Modo voz |
|---|---|---|
| Entrada | Escribe en la caja de texto o toca una sugerencia | Toca el micrófono y habla |
| Salida | Respuesta en texto en el chat | Respuesta en texto **y leída en voz alta** |
| Pensado para | Quien prefiere leer, lugares con ruido | Personas adultas con poca práctica escribiendo, discapacidad visual o motriz |
| Tecnología | Caja de texto normal | `SpeechRecognition` (voz → texto, `es-PE`) y `speechSynthesis` (texto → voz) del navegador |

Reglas:
- Los dos modos usan **el mismo asistente** por detrás; solo cambia cómo entra y sale el mensaje.
- En modo voz, el texto reconocido se muestra antes de enviarlo, para que el usuario vea si se entendió bien.
- En modo voz, las confirmaciones también se pueden decir ("sí, publícala") además de tocar el botón.
- Se puede cambiar de modo en cualquier momento, y el lector de voz se puede pausar o repetir.
- Si el navegador no soporta voz, se avisa y queda el modo escrito.
- Funciona en **celular** (panel que sube desde abajo) y en **PC** (panel lateral). En PC el modo voz necesita
  micrófono; si no hay, se usa el modo escrito.

## Cómo se "entrena": modelo pre-entrenado + especialización

No se entrena un modelo desde cero (es muy caro y no hace falta). Se parte de un **modelo ya entrenado**
que entiende español y se **especializa** para el aula virtual en dos etapas.

### Etapa 1 — Especializar sin tocar el modelo (lanzamiento)

1. **Instrucciones del sistema (prompt):** quién es, a quién ayuda, que hable simple, frases cortas, en español
   peruano, con paciencia, y que **siempre pida confirmación** antes de guardar o enviar algo.
2. **Base de conocimiento (RAG):** el manual de uso del aula (docente y alumno) y preguntas frecuentes. En cada
   consulta se le pasa solo la parte relevante.
3. **Herramientas (function calling):** una lista cerrada de acciones que el asistente puede pedir.
   El modelo **no toca la base de datos**: pide la acción y el backend PHP la ejecuta con los mismos permisos
   del usuario.
4. **Pruebas:** una lista de pedidos reales (ej. "kiero subir mi tarea") con la respuesta esperada, que se corre
   antes de cada cambio.

Con esto el asistente ya funciona para el CETPRO. Durante esta etapa se guardan las conversaciones en
`av_asistente_logs` (con aviso al usuario y sin datos personales sensibles).

### Etapa 2 — Ajuste fino (fine-tuning) con datos reales

Cuando haya varias semanas de uso, se revisan los logs para ver en qué falla (no entiende cómo escriben o hablan
los alumnos, responde muy largo, elige mal la acción) y se **ajusta el modelo** con ejemplos del propio sistema.

**Cómo preparar los datos:**
1. Exportar conversaciones de `av_asistente_logs`.
2. Quitar nombres, DNI y cualquier dato personal.
3. Corregir a mano la respuesta o acción correcta en cada caso.
4. Juntar algunos cientos de ejemplos variados (docente y alumno, escrito y voz, con errores de ortografía).
5. Separar un 10–20 % para probar que el modelo ajustado responde mejor que el de la etapa 1.

Formato de cada ejemplo (JSONL):
```json
{"rol": "alumno", "pedido": "kiero subir mi tarea de corte", "respuesta": "Abrí tu tarea \"Foto de corte degrafilado\". Toca el botón grande \"Tomar foto\" y luego \"Enviar tarea\".", "herramienta": "abrir_pantalla", "args": {"pantalla": "tarea", "tarea_id": 12}}
{"rol": "docente", "pedido": "quienes no me han mandado la tarea", "respuesta": "Faltan Carlos y Jorge. ¿Les mando un recordatorio por WhatsApp?", "herramienta": "listar_sin_entrega", "args": {"tarea_id": 12}}
```

**Opciones para el ajuste fino:**

| Opción | Ventaja | Desventaja |
|---|---|---|
| Modelo en la nube con fine-tuning por API | Fácil, no necesita servidor propio | Costo por uso, depende del proveedor |
| Modelo abierto (Llama, Qwen, Mistral) ajustado con LoRA | Es propio, sin pago por mensaje | Necesita servidor con GPU para correr rápido; el Windows Server actual probablemente no la tiene |

La decisión entre ambas se toma en la etapa 2, según presupuesto y resultados de la etapa 1.

## Herramientas (acciones permitidas)

| Herramienta | Rol | Confirmación |
|---|---|---|
| `abrir_pantalla(pantalla, curso_id)` | Todos | No |
| `listar_pendientes()` | Alumno | No |
| `ver_notas(curso_id)` | Alumno, Docente | No |
| `leer_anuncios(curso_id)` | Todos | No |
| `cambiar_accesibilidad(letra, contraste, voz)` | Todos | No |
| `buscar_ayuda(pregunta)` | Todos | No |
| `borrador_tarea(curso_id, titulo, instrucciones, fecha)` | Docente | **Sí, antes de publicar** |
| `listar_sin_entrega(tarea_id)` | Docente | No |
| `abrir_asistencia(curso_id, fecha)` | Docente | No |
| `generar_reporte(curso_id, formato)` | Docente | No |

El asistente **nunca** califica, borra, publica ni envía nada sin que el usuario toque "Confirmar".

## Arquitectura

```
Celular ──(texto o voz)──► Asistente (JS en el navegador)
                              │  voz → texto: Web Speech API
                              ▼
                     PHP: AsistenteController
                       - verifica sesión y rol
                       - arma el prompt + manual + herramientas del rol
                       - llama a la API del modelo de IA
                       - ejecuta la herramienta pedida (con permisos)
                       - guarda el log
                              │
                              ▼
                     Respuesta + acción (abrir pantalla, etc.)
                              │  texto → voz: speechSynthesis
                              ▼
                           Usuario
```

- **Voz:** Web Speech API del navegador (`SpeechRecognition` en `es-PE`, `speechSynthesis` para leer).
  Gratis y funciona en Chrome de Android.
- **Modelo de IA:** cualquier proveedor con API y function calling. La clave de API va **solo en el servidor**
  (`config.php`), nunca en el JavaScript.

## Seguridad y privacidad

- Al modelo se le manda **solo lo necesario** (nombre de pila, cursos, tareas); nunca DNI, contraseñas ni datos
  de discapacidad.
- Las herramientas usan los mismos controladores y permisos que el resto del sistema: un alumno no puede pedir
  notas de otro.
- Límite de mensajes por usuario al día para controlar el costo.
- Log de conversaciones (`av_asistente_logs`) para mejorar respuestas; se informa al usuario y se borra
  pasado un tiempo.
- Si la IA no responde, aparece un mensaje claro y los botones normales siguen funcionando.

## Tablas nuevas

| Tabla | Descripción |
|---|---|
| `av_preferencias` | Configuración de accesibilidad por usuario (tamaño de letra, contraste, voz) |
| `av_asistente_logs` | Pedido, herramienta usada, respuesta y fecha |

## Pendiente de decidir

- [ ] Proveedor del modelo de IA y presupuesto mensual
- [ ] Opción de ajuste fino para la etapa 2 (nube o modelo abierto)
- [ ] Límite de mensajes por usuario
- [ ] Probar con alumnos adultos y con alumnos con discapacidad antes de lanzarlo
