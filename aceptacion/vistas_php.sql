-- Vistas con los nombres de tablas y columnas del sistema anterior (PHP), para que sus guiones de prueba puedan hacer
-- SELECT sin cambiar sus consultas. Solo existen en la base de aceptación.
CREATE VIEW av_preguntas AS
  SELECT id, formulario_id AS cuestionario_id, tipo, enunciado, orden, puntos, obligatoria::int AS obligatoria FROM formularios_pregunta;
CREATE VIEW av_opciones AS
  SELECT id, pregunta_id, grupo, texto, correcta::int AS correcta, orden FROM formularios_opcion;
CREATE VIEW cursos AS
  SELECT id, docente_id, nombre, especialidad, modulo, periodo, turno FROM academico_modulo;
