-- Aula Virtual CETPRO Mangomarca - Esquema inicial
-- MySQL 8 / MariaDB

SET NAMES utf8mb4; -- las tildes y la ñ se guardan bien aunque se importe desde PowerShell
CREATE DATABASE IF NOT EXISTS aula_virtual CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE aula_virtual;

-- ===== Tablas base (pueden venir del Sistema de Gestión) =====

CREATE TABLE IF NOT EXISTS usuarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  dni CHAR(8) NULL UNIQUE,               -- opcional; se puede entrar con DNI o con correo
  nombres VARCHAR(100) NOT NULL,
  apellidos VARCHAR(100) NOT NULL DEFAULT '',
  correo VARCHAR(120) NULL UNIQUE,       -- forma principal de entrar
  telefono VARCHAR(15),
  password_hash VARCHAR(255) NOT NULL,   -- vacío = alumno cargado en lista que aún no creó su contraseña
  rol ENUM('admin','direccion','docente','alumno') NOT NULL,
  activo TINYINT(1) NOT NULL DEFAULT 1,
  es_prueba TINYINT(1) NOT NULL DEFAULT 0, -- creado desde el panel "Entrar para probar"
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS cursos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(150) NOT NULL,
  especialidad VARCHAR(100) NOT NULL,
  modulo VARCHAR(100),
  periodo VARCHAR(20) NOT NULL,          -- ej. 2026-II
  turno ENUM('mañana','tarde','noche') NOT NULL,
  horario VARCHAR(120),                  -- ej. Lunes a viernes · 8:00 a 13:00
  docente_id INT NOT NULL,
  activo TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (docente_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS matriculas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  curso_id INT NOT NULL,
  alumno_id INT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_matricula (curso_id, alumno_id),
  FOREIGN KEY (curso_id) REFERENCES cursos(id) ON DELETE CASCADE,
  FOREIGN KEY (alumno_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

-- ===== Tablas del aula virtual =====

CREATE TABLE IF NOT EXISTS av_unidades (
  id INT AUTO_INCREMENT PRIMARY KEY,
  curso_id INT NOT NULL,
  titulo VARCHAR(150) NOT NULL,          -- ej. Clase 1 - Introducción
  descripcion TEXT NULL,                 -- qué aprenderán en la clase
  orden INT NOT NULL DEFAULT 1,
  visible TINYINT(1) NOT NULL DEFAULT 1,
  fecha_inicio DATE NULL,                -- se abre sola este día (NULL = desde ya)
  fecha_fin DATE NULL,                   -- se cierra sola después de este día (NULL = sin fin)
  estado ENUM('auto','abierta','cerrada') NOT NULL DEFAULT 'auto', -- auto = según las fechas; o el docente la abre/cierra
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (curso_id) REFERENCES cursos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_materiales (
  id INT AUTO_INCREMENT PRIMARY KEY,
  unidad_id INT NOT NULL,
  titulo VARCHAR(150) NOT NULL,
  descripcion TEXT,
  tipo ENUM('archivo','enlace','video') NOT NULL,
  archivo_ruta VARCHAR(255),             -- nombre aleatorio en storage/uploads
  archivo_nombre VARCHAR(255),           -- nombre original
  url VARCHAR(500),
  visible_desde DATETIME,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  eliminado_at DATETIME NULL,           -- en la papelera (se recupera durante 30 días)
  FOREIGN KEY (unidad_id) REFERENCES av_unidades(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_tareas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  unidad_id INT NOT NULL,
  titulo VARCHAR(150) NOT NULL,
  instrucciones TEXT,
  criterios TEXT NULL,                   -- lo que el docente revisará (uno por línea)
  archivo_ruta VARCHAR(255),
  archivo_nombre VARCHAR(255),
  fecha_limite DATETIME NOT NULL,
  puntaje_max DECIMAL(4,2) NOT NULL DEFAULT 20.00,
  politica_tardia ENUM('no_acepta','acepta','penalidad') NOT NULL DEFAULT 'no_acepta',
  penalidad_puntos DECIMAL(4,2) NOT NULL DEFAULT 0.00,   -- puntos que se restan si es tardía
  tipo_calificacion ENUM('nota','rubrica','aprobado') NOT NULL DEFAULT 'nota',
  tipo ENUM('individual','grupal') NOT NULL DEFAULT 'individual',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  eliminado_at DATETIME NULL,           -- en la papelera
  FOREIGN KEY (unidad_id) REFERENCES av_unidades(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_entregas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tarea_id INT NOT NULL,
  alumno_id INT NOT NULL,
  archivo_ruta VARCHAR(255),
  archivo_nombre VARCHAR(255),
  enlace VARCHAR(500),
  comentario_alumno TEXT,
  fecha_entrega DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  tardia TINYINT(1) NOT NULL DEFAULT 0,
  nota DECIMAL(4,2),                     -- para 'nota' y 'rubrica' (0–20)
  aprobado TINYINT(1),                   -- para 'aprobado'
  comentario_docente TEXT,
  calificado_at DATETIME,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_entrega (tarea_id, alumno_id),
  retro_ruta VARCHAR(255) NULL,         -- archivo o foto que devuelve el docente
  retro_nombre VARCHAR(255) NULL,
  FOREIGN KEY (tarea_id) REFERENCES av_tareas(id) ON DELETE CASCADE,
  FOREIGN KEY (alumno_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_sesiones (
  id INT AUTO_INCREMENT PRIMARY KEY,
  curso_id INT NOT NULL,
  fecha DATE NOT NULL,
  tema VARCHAR(200),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_sesion (curso_id, fecha),
  FOREIGN KEY (curso_id) REFERENCES cursos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_asistencias (
  id INT AUTO_INCREMENT PRIMARY KEY,
  sesion_id INT NOT NULL,
  alumno_id INT NOT NULL,
  estado ENUM('presente','tarde','falta','justificada') NOT NULL,
  observacion VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_asistencia (sesion_id, alumno_id),
  FOREIGN KEY (sesion_id) REFERENCES av_sesiones(id) ON DELETE CASCADE,
  FOREIGN KEY (alumno_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_anuncios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  curso_id INT NOT NULL,
  autor_id INT NOT NULL,
  titulo VARCHAR(150) NOT NULL,
  contenido TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (curso_id) REFERENCES cursos(id) ON DELETE CASCADE,
  FOREIGN KEY (autor_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_preferencias (
  usuario_id INT PRIMARY KEY,
  tamano_letra ENUM('normal','grande','muy_grande') NOT NULL DEFAULT 'normal',
  alto_contraste TINYINT(1) NOT NULL DEFAULT 0,
  lectura_voz TINYINT(1) NOT NULL DEFAULT 0,
  modo_asistente ENUM('escrito','voz') NOT NULL DEFAULT 'escrito',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_asistente_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  pedido TEXT NOT NULL,
  herramienta VARCHAR(60),               -- acción que pidió la IA (si hubo)
  respuesta TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_notificaciones (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  mensaje VARCHAR(255) NOT NULL,
  enlace VARCHAR(255),
  leida TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_usuario (usuario_id, leida, created_at),
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ===== Mensajería (alumno ↔ docente, dentro de un curso) =====

CREATE TABLE IF NOT EXISTS av_conversaciones (
  id INT AUTO_INCREMENT PRIMARY KEY,
  curso_id INT NOT NULL,
  docente_id INT NOT NULL,
  alumno_id INT NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_conversacion (curso_id, docente_id, alumno_id),
  FOREIGN KEY (curso_id) REFERENCES cursos(id) ON DELETE CASCADE,
  FOREIGN KEY (docente_id) REFERENCES usuarios(id) ON DELETE CASCADE,
  FOREIGN KEY (alumno_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_mensajes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  conversacion_id INT NOT NULL,
  autor_id INT NOT NULL,
  texto TEXT NOT NULL,
  leido_at DATETIME,
  archivo_ruta VARCHAR(255) NULL,        -- foto o archivo adjunto al mensaje
  archivo_nombre VARCHAR(255) NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  KEY idx_conversacion (conversacion_id, created_at),
  FOREIGN KEY (conversacion_id) REFERENCES av_conversaciones(id) ON DELETE CASCADE,
  FOREIGN KEY (autor_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ===== Formularios: exámenes, trabajos y encuestas (como Google Forms) =====

CREATE TABLE IF NOT EXISTS av_cuestionarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  unidad_id INT NOT NULL,
  modo ENUM('examen','trabajo','encuesta') NOT NULL DEFAULT 'examen',
                                          -- examen: puntos y nota automática · trabajo: el docente pone la nota · encuesta: sin nota
  titulo VARCHAR(150) NOT NULL,
  instrucciones TEXT,
  mensaje_final VARCHAR(500),             -- mensaje que ve el alumno al enviar
  fecha_inicio DATETIME,                  -- desde cuándo se puede responder (NULL = desde que se publica)
  fecha_limite DATETIME NOT NULL,
  tiempo_minutos INT,                     -- NULL = sin límite de tiempo
  intentos_max INT NOT NULL DEFAULT 1,
  mezclar TINYINT(1) NOT NULL DEFAULT 0,  -- cambia el orden de preguntas y alternativas
  mostrar_respuestas TINYINT(1) NOT NULL DEFAULT 1, -- al terminar, el alumno ve qué respondió bien
  publicado TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  eliminado_at DATETIME NULL,           -- en la papelera
  FOREIGN KEY (unidad_id) REFERENCES av_unidades(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_preguntas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  cuestionario_id INT NOT NULL,
  tipo ENUM('opcion','multiple','vf','desplegable','corta','abierta','escala','fecha','hora','archivo',
            'cuadricula','cuadricula_casillas','seccion') NOT NULL,
  enunciado TEXT NOT NULL,
  ayuda VARCHAR(500),                     -- descripción debajo de la pregunta
  imagen_ruta VARCHAR(255),               -- foto opcional de la pregunta (en storage/uploads)
  obligatoria TINYINT(1) NOT NULL DEFAULT 1,
  puntos DECIMAL(5,2) NOT NULL DEFAULT 1.00,
  respuestas_aceptadas TEXT,              -- solo 'corta' en examen: una respuesta válida por línea
  explicacion TEXT,                       -- examen: se muestra al alumno al terminar
  permite_otra TINYINT(1) NOT NULL DEFAULT 0, -- alternativas: agrega "Otra" con texto libre
  escala_min TINYINT,
  escala_max TINYINT,
  etiqueta_min VARCHAR(60),
  etiqueta_max VARCHAR(60),
  orden INT NOT NULL DEFAULT 1,
  FOREIGN KEY (cuestionario_id) REFERENCES av_cuestionarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_opciones (
  id INT AUTO_INCREMENT PRIMARY KEY,
  pregunta_id INT NOT NULL,
  grupo ENUM('opcion','fila','columna') NOT NULL DEFAULT 'opcion', -- filas y columnas: preguntas de cuadrícula
  texto VARCHAR(500) NOT NULL,
  correcta TINYINT(1) NOT NULL DEFAULT 0,
  orden INT NOT NULL DEFAULT 1,
  FOREIGN KEY (pregunta_id) REFERENCES av_preguntas(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_intentos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  cuestionario_id INT NOT NULL,
  alumno_id INT NOT NULL,
  inicio DATETIME NOT NULL,
  fin DATETIME,                           -- NULL = todavía respondiendo
  fuera_tiempo TINYINT(1) NOT NULL DEFAULT 0,
  puntaje DECIMAL(6,2),
  puntaje_max DECIMAL(6,2),
  nota DECIMAL(4,2),                      -- 0–20; NULL mientras falte revisar (o si es encuesta)
  revisado TINYINT(1) NOT NULL DEFAULT 0,
  comentario TEXT,                        -- comentario general del docente
  FOREIGN KEY (cuestionario_id) REFERENCES av_cuestionarios(id) ON DELETE CASCADE,
  FOREIGN KEY (alumno_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS av_respuestas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  intento_id INT NOT NULL,
  pregunta_id INT NOT NULL,
  opciones VARCHAR(255),                  -- ids de las alternativas marcadas, separados por coma
  texto TEXT,                             -- texto, fecha, hora, número de escala, "Otra" o cuadrícula (JSON)
  archivo_ruta VARCHAR(255),              -- pregunta de tipo archivo
  archivo_nombre VARCHAR(255),
  puntos DECIMAL(5,2),                    -- NULL = falta revisar
  comentario VARCHAR(500),
  UNIQUE KEY uq_respuesta (intento_id, pregunta_id),
  FOREIGN KEY (intento_id) REFERENCES av_intentos(id) ON DELETE CASCADE,
  FOREIGN KEY (pregunta_id) REFERENCES av_preguntas(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ===== Versión 2: inscripción, perfiles, configuración y seguridad =====

-- Código que el docente da a sus alumnos para inscribirse en su módulo (curso).
CREATE TABLE IF NOT EXISTS av_inscripcion (
  curso_id INT PRIMARY KEY,
  codigo CHAR(7) NOT NULL UNIQUE,         -- ej. PEL4821 (se muestra PEL-4821)
  abierta TINYINT(1) NOT NULL DEFAULT 1,  -- 0 = ya no se aceptan alumnos nuevos con el código
  whatsapp_grupo VARCHAR(300) NULL,       -- enlace del grupo de WhatsApp del módulo (opcional)
  FOREIGN KEY (curso_id) REFERENCES cursos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Datos extra de la persona (sin datos de discapacidad).
CREATE TABLE IF NOT EXISTS av_perfiles (
  usuario_id INT PRIMARY KEY,
  fecha_nacimiento DATE NULL,
  origen ENUM('admin','lista','registro') NOT NULL DEFAULT 'admin', -- cómo se creó la cuenta
  activado_at DATETIME NULL,              -- cuándo el alumno creó su contraseña
  cambiar_clave TINYINT(1) NOT NULL DEFAULT 0, -- 1 = debe elegir su contraseña al entrar (la que le dieron era temporal)
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Quién hizo qué: accesos, contraseñas, cuentas, notas, ajustes y módulos.
CREATE TABLE IF NOT EXISTS av_registro (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NULL,
  accion VARCHAR(30) NOT NULL,
  detalle VARCHAR(255) NOT NULL,
  ip VARCHAR(45) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_registro_fecha (created_at),
  KEY idx_registro_accion (accion, created_at),
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Ajustes del aula que cambia el administrador (colores, logo, textos, especialidades…).
CREATE TABLE IF NOT EXISTS av_configuracion (
  clave VARCHAR(60) PRIMARY KEY,
  valor TEXT NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Intentos fallidos de entrar o registrarse (para frenar a quien prueba contraseñas o códigos).
CREATE TABLE IF NOT EXISTS av_accesos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  clave VARCHAR(100) NOT NULL,            -- ej. login:12345678, codigo:ip:1.2.3.4
  created_at DATETIME NOT NULL,
  INDEX idx_clave (clave, created_at)
) ENGINE=InnoDB;

-- ===== Versión 3 =====

CREATE TABLE IF NOT EXISTS av_evaluacion (
  curso_id INT PRIMARY KEY,
  peso_tareas TINYINT UNSIGNED NOT NULL DEFAULT 50,      -- trabajos con foto o archivo
  peso_tests TINYINT UNSIGNED NOT NULL DEFAULT 30,       -- formularios con nota
  peso_asistencia TINYINT UNSIGNED NOT NULL DEFAULT 20,  -- % de asistencia llevado a 0–20
  nota_minima DECIMAL(4,2) NOT NULL DEFAULT 11.00,
  FOREIGN KEY (curso_id) REFERENCES cursos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Preguntas de la clase: los alumnos preguntan; el docente y los compañeros responden.
CREATE TABLE IF NOT EXISTS av_preguntas_clase (
  id INT AUTO_INCREMENT PRIMARY KEY,
  unidad_id INT NOT NULL,
  autor_id INT NOT NULL,
  padre_id INT NULL,                       -- NULL = pregunta; si no, respuesta a esa pregunta
  texto TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_unidad (unidad_id, padre_id),
  FOREIGN KEY (unidad_id) REFERENCES av_unidades(id) ON DELETE CASCADE,
  FOREIGN KEY (autor_id) REFERENCES usuarios(id),
  FOREIGN KEY (padre_id) REFERENCES av_preguntas_clase(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ===== Versión 7 =====

-- Unidades didácticas de cada módulo (como en el plan de estudios: nombre, créditos y horas).
CREATE TABLE IF NOT EXISTS av_unidades_didacticas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  curso_id INT NOT NULL,                 -- el módulo al que pertenece (tabla cursos)
  nombre VARCHAR(150) NOT NULL,
  creditos TINYINT UNSIGNED NULL,
  horas SMALLINT UNSIGNED NULL,
  orden SMALLINT NOT NULL DEFAULT 0,
  INDEX idx_modulo (curso_id, orden),
  FOREIGN KEY (curso_id) REFERENCES cursos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Actualizaciones de la base ya aplicadas (las aplica src/herramientas/migrar.php)
CREATE TABLE IF NOT EXISTS av_migraciones (
  archivo VARCHAR(120) PRIMARY KEY,
  aplicado_at DATETIME NOT NULL
) ENGINE=InnoDB;
INSERT IGNORE INTO av_migraciones (archivo, aplicado_at) VALUES
  ('2026-10-07-correo-mensajes-examenes.sql', NOW()),
  ('2026-10-07-formularios.sql', NOW()),
  ('2026-10-10-version-2.sql', NOW()),
  ('2026-10-11-version-3.sql', NOW()),
  ('2026-10-12-version-4.sql', NOW()),
  ('2026-10-13-version-5.sql', NOW()),
  ('2026-10-14-version-6.sql', NOW());
