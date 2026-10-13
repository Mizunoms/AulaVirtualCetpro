# 01 - Visión del proyecto

## Problema

Hoy los docentes del CETPRO Mangomarca trabajan cada uno a su manera: dejan tareas por WhatsApp, reciben
entregas como fotos o archivos sueltos, llevan la asistencia y las notas en cuaderno o Excel, y arman los
reportes para dirección a mano. La información queda dispersa, se pierden entregas y cuesta saber cómo va cada alumno.

## Solución

Un aula virtual propia del CETPRO donde cada curso tenga un espacio con:

- Materiales del curso (PDF, videos, enlaces, diapositivas)
- Tareas con fecha límite y entrega de archivos
- Cuestionarios en línea
- Registro de asistencia
- Libro de calificaciones y reportes
- Anuncios para el grupo

## Objetivos

1. Centralizar en un solo lugar materiales, tareas, notas y asistencia.
2. Reducir el tiempo que el docente dedica a recibir, ordenar y calificar trabajos.
3. Dar al alumno una vista clara de qué tiene pendiente y cómo va.
4. Generar reportes para dirección sin trabajo manual.
5. Funcionar bien en celular y en PC: el celular es prioridad porque muchos alumnos solo tienen ese
   dispositivo, y en PC se aprovecha la pantalla grande (tablas de notas, asistencia, reportes).

## Usuarios

Entre los alumnos hay **personas adultas** y **personas con discapacidad**, por eso el sistema prioriza la
accesibilidad y suma un **asistente virtual con IA** que ayuda a usarlo por voz o texto
(ver [07 - Asistente IA](07-asistente-ia.md)).

| Rol | Qué hace |
|---|---|
| **Administrador** | Gestiona usuarios, cursos, periodos y configuración general |
| **Dirección / Coordinación** | Ve reportes de notas y asistencia de todos los cursos |
| **Docente** | Administra sus cursos: materiales, tareas, cuestionarios, asistencia y notas |
| **Alumno** | Ve materiales, entrega tareas, rinde cuestionarios, revisa notas |

## Alcance

**Incluye (versión 1):** cursos, materiales, tareas y entregas, calificaciones, asistencia, anuncios, reportes básicos.

La versión 1 es **estándar**: todos los cursos tienen el mismo menú y las mismas secciones. Después de las
encuestas se agregan secciones especiales por especialidad. Ver [08 - Análisis de Blackboard](08-analisis-blackboard.md).

**Fuera del alcance inicial:** videoconferencias, chat en tiempo real, app móvil nativa, pagos.
Se evaluarán para versiones posteriores según lo que salga de las entrevistas.

## Relación con el Sistema de Gestión

El CETPRO ya cuenta con un sistema de gestión (matrícula, alumnos, profesores, cursos). El aula virtual debe
reutilizar esos datos para no registrar dos veces a alumnos y docentes. La forma de integración
(misma base de datos o sincronización) se define en [03 - Arquitectura](03-arquitectura.md).
