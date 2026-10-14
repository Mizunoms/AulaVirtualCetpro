# Puesta en marcha: de «instalado» a «lo usa el CETPRO»

El aula empieza **vacía**, sin datos del piloto. Esta guía dice en qué orden dejarla lista, cómo probarla con
un profesor y un celular de verdad, y cómo abrirla a todos. Primero se instala en el servidor
([02-servidor-windows.md](02-servidor-windows.md)); si todavía no está, estos pasos también sirven en una PC de prueba.

---

## 1. Dejar el aula lista (la hace quien administra, ~1 hora)

| # | Qué | Dónde |
|---|---|---|
| 1 | Entrar con el administrador (el que se creó con `createsuperuser`) | `/login?como=personal` |
| 2 | **Ajustes → Identidad**: nombre del CETPRO, logo, colores, WhatsApp de ayuda, periodo (ej. 2026-II) | Ajustes |
| 3 | **Ajustes → Cursos**: la lista de cursos (programas de estudio) del CETPRO | Ajustes |
| 4 | **Crear a los docentes** (primero ellos, porque cada módulo lleva un docente): **Nuevo docente**, o todos de una vez con **Cargar lista de docentes** (Excel, CSV o lista pegada). Al terminar, el aula muestra su contraseña temporal **una sola vez**: envíasela por el botón de WhatsApp o cópiala | Personas |
| 5 | **Crear los módulos**: con el botón **Cargar plan de estudios (Excel)** (Excel del Ministerio) o uno por uno con **Nuevo módulo**; ahí se elige su docente | Cursos |
| 6 | Avisar a cada docente por WhatsApp: entra con su correo y su contraseña temporal, y el aula le pide elegir una propia (puede tocar **Más tarde** y seguir: un aviso amarillo le recuerda crearla, y se la piden otra vez al volver a entrar) | — |
| 7 | Apuntar el **código de inscripción** de cada módulo (ej. `SOP-4821`): los alumnos lo usan para crear su cuenta | Módulo (en la lista de Cursos) |
| 8 | Programar el **respaldo** (ver la Parte 9 de la guía del servidor) | Servidor |

> Los alumnos **no hace falta cargarlos antes**: cada uno puede crear su cuenta con su DNI y el código del módulo.
> Si prefieres tenerlos listos, usa **Personas → Cargar lista de alumnos** (Excel, CSV o lista pegada) y, en la lista de
> alumnos de cada módulo, **Preparar accesos** (genera las contraseñas temporales y las manda por WhatsApp).

---

## 2. Prueba con 1 profesor y 2 alumnos (antes de abrirla a todos, ~1 hora)

Lo ideal: **un profesor** de un taller práctico (peluquería, panadería…) y **dos alumnos**, uno de ellos adulto o con
alguna dificultad para usar el celular. Cada uno con **su propio celular**. Mira cómo lo usan **sin ayudarlos** y anota
dónde dudan: eso vale más que cualquier lista.

### El profesor
1. Entra con su contraseña temporal y elige una nueva.
2. Mira su módulo: crea una **clase**, sube un **material** (una foto o un PDF) y deja una **tarea** con fecha límite.
3. Escribe un **aviso** para el módulo.
4. Toma **asistencia** del día.

### Los alumnos
1. Desde el celular, en la pantalla de entrada: **«¿Es tu primera vez? Crea tu contraseña aquí»**, con su DNI y el código del módulo.
2. Entran y ven la tarea. **Toman una foto con la cámara** y la entregan.
3. Abren el material y el aviso. Mandan un **mensaje** al profesor.
4. Si hay un examen o formulario: lo responden hasta el final.

### De nuevo el profesor
1. En **Por calificar** ve la foto, pone una nota y un comentario.
2. El alumno entra a **Mis notas** y la ve.

### El tutorial de primera vez

La primera vez que alguien entra, el aula le muestra un **tutorial corto** (distinto para alumno, docente y administración) que
explica para qué sirve cada parte. Se puede **saltar**, tiene botón **Escuchar** y no vuelve a salir solo. Para verlo otra vez:
**Mi cuenta → Repetir tutorial**, o al final del Inicio. **Ayuda** (también en el menú lateral) trae el resumen del sistema y
las preguntas frecuentes. Observa si la persona lo entiende sin ayuda y qué paso salta.

Si cambias el nombre de un botón del aula, cámbialo también en `apps/nucleo/ayuda.py` (una prueba avisa si quedó mal).

### Lo que solo se puede comprobar con un celular de verdad

- [ ] La foto sale de la **cámara** del celular y llega bien (no girada, no pesada de más).
- [ ] El botón de **WhatsApp** abre la aplicación con el mensaje de accesos ya escrito.
- [ ] Con **internet lento** (datos móviles) la entrega no se corta.
- [ ] Con **TalkBack** (Android → Accesibilidad) se puede entrar, ver la tarea y entregarla, y los botones «suenan» con su nombre.
- [ ] Con **letra «muy grande»** y **alto contraste** (Mi cuenta) todo se sigue leyendo y tocando (en el navegador de una PC ya se revisó; falta verlo en un celular).
- [ ] El **modo oscuro** se ve bien.
- [ ] El **tutorial** se lee bien, el botón **Escuchar** funciona y se puede cerrar con TalkBack.
- [ ] Un alumno **no puede ver** los datos de otro (probar con dos cuentas).

Apunta cada problema con: **quién**, **qué hizo**, **qué esperaba** y **qué pasó** (si puedes, una captura).

---

## 3. Abrirla a todos

1. Corrige lo que salió en la prueba.
2. Avisa a los docentes por WhatsApp con su acceso (**Preparar accesos**) y el enlace del aula.
3. Los alumnos entran con su DNI y el código de su módulo; el primer día, un docente o una persona de la secretaría los
   acompaña con su celular.
4. Revisa a diario la primera semana: en el **Inicio del administrador**, «Ver todo el registro» (accesos y cambios), y que el respaldo se haya hecho.

## 4. Si algo sale mal

- **Una persona no puede entrar:** Personas → buscarla → **Más → Resetear contraseña** (se le da una temporal).
- **Un alumno se equivocó de módulo:** en el módulo correcto agrégalo; en el equivocado, **Quitar** (sus entregas se conservan).
- **Algo no funciona para todos:** mira `C:\aula\logs\aula.log` y la tabla «Si algo sale mal» de la guía del servidor.
- **Hay que volver a un estado anterior:** restaurar el último respaldo (Parte 9 de la guía del servidor).

## 5. Después

- Cada periodo: **archivar** los módulos viejos y copiar los que se repiten (en el módulo, **Copiar módulo**: «Para el siguiente periodo»).
- Copiar la carpeta de respaldos a un USB o a otra PC cada semana.
- Las mejoras nuevas se instalan con la Parte 10 de la guía del servidor (siempre con respaldo antes).
