"""Datos de ejemplo con la forma de la base del sistema anterior (PHP + MariaDB), para probar `migrar_desde_php`.

Las tablas van en el orden en que se pueden cargar (primero lo que no depende de nada). Las horas no llevan zona, como en MySQL.
Hay cuentas del antiguo «modo prueba» (20 y 21) con cosas colgadas, para comprobar que no se pasan.
"""

from datetime import date, datetime
from decimal import Decimal as D

import bcrypt

CLAVES = {"admin": "Admin-clave-1", "rosa": "clave-de-rosa", "ana": "clave-de-ana"}


def hash_php(clave):
    """Una contraseña como la guardaba PHP (`password_hash`): empieza con $2y$."""
    return bcrypt.hashpw(clave.encode(), bcrypt.gensalt(rounds=4)).decode().replace("$2b$", "$2y$", 1)


def _d(*a):
    return datetime(*a)


def datos_origen():
    t0 = _d(2026, 9, 1, 7, 0)
    usuarios = [
        dict(id=1, dni="10000001", nombres="Administrador", apellidos="del Aula", correo="Admin@Cetpro.test", telefono=None,
             password_hash=hash_php(CLAVES["admin"]), rol="admin", activo=1, es_prueba=0, created_at=t0),
        dict(id=2, dni=None, nombres="Dirección", apellidos="CETPRO", correo="direccion@cetpro.test", telefono="",
             password_hash=hash_php("otra-clave-2"), rol="direccion", activo=1, es_prueba=0, created_at=t0),
        dict(id=5, dni="20000001", nombres="Rosa Elena", apellidos="Paredes Huamán", correo="rosa@cetpro.test", telefono="999111222",
             password_hash=hash_php(CLAVES["rosa"]), rol="docente", activo=1, es_prueba=0, created_at=t0),
        dict(id=7, dni="20000002", nombres="Pedro", apellidos="Huaranga Soto", correo="pedro@cetpro.test", telefono=None,
             password_hash=hash_php("clave-de-pedro"), rol="docente", activo=1, es_prueba=0, created_at=t0),
        dict(id=10, dni="71234567", nombres="Ana María", apellidos="Quispe Rojas", correo=None, telefono="987654321",
             password_hash=hash_php(CLAVES["ana"]), rol="alumno", activo=1, es_prueba=0, created_at=_d(2026, 9, 1, 8, 0)),
        dict(id=11, dni="71234568", nombres="Luis Fernando", apellidos="Mamani Torres", correo="", telefono="987000111",
             password_hash="", rol="alumno", activo=1, es_prueba=0, created_at=_d(2026, 9, 1, 8, 5)),
        dict(id=12, dni="71234569", nombres="Eva", apellidos="Díaz Vega", correo=None, telefono=None,
             password_hash=hash_php("clave-de-eva"), rol="alumno", activo=0, es_prueba=0, created_at=_d(2026, 9, 1, 8, 10)),
        dict(id=20, dni=None, nombres="Docente", apellidos="de prueba", correo="prueba-d@prueba.local", telefono=None,
             password_hash=hash_php("x-prueba-1"), rol="docente", activo=1, es_prueba=1, created_at=t0),
        dict(id=21, dni=None, nombres="Alumno", apellidos="de prueba", correo="prueba-x@prueba.local", telefono=None,
             password_hash=hash_php("x-prueba-2"), rol="alumno", activo=1, es_prueba=1, created_at=t0),
    ]  # fmt: skip
    return {
        "usuarios": usuarios,
        "av_perfiles": [
            dict(usuario_id=5, fecha_nacimiento=None, origen="admin", activado_at=None, cambiar_clave=1),
            dict(usuario_id=10, fecha_nacimiento=date(1990, 5, 17), origen="registro", activado_at=_d(2026, 9, 1, 8, 30), cambiar_clave=0),
            dict(usuario_id=11, fecha_nacimiento=None, origen="lista", activado_at=None, cambiar_clave=0),
            dict(usuario_id=12, fecha_nacimiento=None, origen="lista", activado_at=_d(2026, 9, 2, 9, 0), cambiar_clave=1),
        ],
        "av_preferencias": [
            dict(usuario_id=10, tamano_letra="grande", alto_contraste=1, lectura_voz=1, modo_asistente="voz", updated_at=_d(2026, 9, 2, 10, 0)),
            dict(usuario_id=21, tamano_letra="normal", alto_contraste=0, lectura_voz=0, modo_asistente="escrito", updated_at=t0),
        ],
        "cursos": [
            dict(id=3, nombre="Peluquería – Módulo I", especialidad="Peluquería y Barbería", modulo="Módulo I", periodo="2026-II",
                 turno="mañana", horario="8:00 a. m. a 1:00 p. m.", docente_id=5, activo=1, created_at=t0),
            dict(id=4, nombre="Panadería – Módulo I", especialidad="Panadería y Pastelería", modulo=None, periodo="2026-I",
                 turno="noche", horario=None, docente_id=7, activo=0, created_at=t0),
            dict(id=8, nombre="Módulo de prueba", especialidad="Prueba", modulo="Módulo I", periodo="2026-II",
                 turno="tarde", horario="", docente_id=20, activo=1, created_at=t0),
        ],  # fmt: skip
        "av_inscripcion": [
            dict(curso_id=3, codigo="PEL4821", abierta=1, whatsapp_grupo="https://chat.whatsapp.com/grupo-pelu"),
            dict(curso_id=8, codigo="PRU1111", abierta=1, whatsapp_grupo=None),
        ],
        "matriculas": [
            dict(id=1, curso_id=3, alumno_id=10, created_at=_d(2026, 9, 1, 9, 0)),
            dict(id=2, curso_id=3, alumno_id=11, created_at=_d(2026, 9, 1, 9, 1)),
            dict(id=3, curso_id=3, alumno_id=12, created_at=_d(2026, 9, 1, 9, 2)),
            dict(id=4, curso_id=4, alumno_id=10, created_at=_d(2026, 9, 1, 9, 3)),
            dict(id=5, curso_id=3, alumno_id=21, created_at=t0),
            dict(id=6, curso_id=8, alumno_id=10, created_at=t0),
        ],
        "av_unidades_didacticas": [
            dict(id=1, curso_id=3, nombre="Corte básico", creditos=3, horas=48, orden=1),
            dict(id=2, curso_id=3, nombre="Tinte", creditos=None, horas=None, orden=2),
            dict(id=3, curso_id=8, nombre="Unidad de prueba", creditos=1, horas=16, orden=1),
        ],
        "av_evaluacion": [
            dict(curso_id=3, peso_tareas=40, peso_tests=40, peso_asistencia=20, nota_minima=D("12.00")),
            dict(curso_id=8, peso_tareas=50, peso_tests=30, peso_asistencia=20, nota_minima=D("11.00")),
        ],
        "av_unidades": [
            dict(id=100, curso_id=3, titulo="Clase 1 – Higiene", descripcion="Lo básico del taller", orden=1, visible=1,
                 fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30), estado="auto", created_at=t0),
            dict(id=101, curso_id=3, titulo="Clase 2 – Corte", descripcion=None, orden=2, visible=0,
                 fecha_inicio=None, fecha_fin=None, estado="cerrada", created_at=t0),
            dict(id=102, curso_id=4, titulo="Clase 1 – Masas", descripcion="", orden=1, visible=1,
                 fecha_inicio=None, fecha_fin=None, estado="abierta", created_at=t0),
            dict(id=103, curso_id=8, titulo="Clase de prueba", descripcion=None, orden=1, visible=1,
                 fecha_inicio=None, fecha_fin=None, estado="auto", created_at=t0),
        ],  # fmt: skip
        "av_materiales": [
            dict(id=1000, unidad_id=100, titulo="Guía de higiene", descripcion="PDF", tipo="archivo", archivo_ruta="2026/09/aaaa.pdf",
                 archivo_nombre="Guía.pdf", url=None, created_at=t0, eliminado_at=None),
            dict(id=1001, unidad_id=100, titulo="Video del corte", descripcion=None, tipo="video", archivo_ruta=None,
                 archivo_nombre=None, url="https://youtu.be/abc", created_at=t0, eliminado_at=None),
            dict(id=1002, unidad_id=100, titulo="Material en la papelera", descripcion=None, tipo="enlace", archivo_ruta=None,
                 archivo_nombre=None, url="https://ejemplo.pe", created_at=t0, eliminado_at=_d(2026, 10, 1, 12, 0)),
            dict(id=1003, unidad_id=101, titulo="Ruta sospechosa", descripcion=None, tipo="archivo", archivo_ruta="../fuera.txt",
                 archivo_nombre="fuera.txt", url=None, created_at=t0, eliminado_at=None),
        ],  # fmt: skip
        "av_tareas": [
            dict(id=2000, unidad_id=100, titulo="Hoja de operaciones", instrucciones="Toma una foto de tu hoja.", criterios=None,
                 archivo_ruta="2026/09/tarea.pdf", archivo_nombre="Ejemplo.pdf", fecha_limite=_d(2026, 9, 20, 23, 59),
                 puntaje_max=D("20.00"), politica_tardia="penalidad", penalidad_puntos=D("2.00"), tipo_calificacion="nota",
                 tipo="individual", created_at=t0, eliminado_at=None),
            dict(id=2001, unidad_id=101, titulo="Foto del corte", instrucciones=None, criterios="Limpieza|5\nPrecisión|5",
                 archivo_ruta=None, archivo_nombre=None, fecha_limite=_d(2026, 9, 25, 23, 59), puntaje_max=D("20.00"),
                 politica_tardia="no_acepta", penalidad_puntos=D("0.00"), tipo_calificacion="rubrica", tipo="grupal",
                 created_at=t0, eliminado_at=None),
            dict(id=2002, unidad_id=103, titulo="Tarea de prueba", instrucciones=None, criterios=None, archivo_ruta=None,
                 archivo_nombre=None, fecha_limite=_d(2026, 9, 25, 23, 59), puntaje_max=D("20.00"), politica_tardia="acepta",
                 penalidad_puntos=D("0.00"), tipo_calificacion="aprobado", tipo="individual", created_at=t0, eliminado_at=None),
        ],  # fmt: skip
        "av_entregas": [
            dict(id=3000, tarea_id=2000, alumno_id=10, archivo_ruta="2026/09/ent.jpg", archivo_nombre="mi hoja.jpg", enlace=None,
                 comentario_alumno="Aquí está", fecha_entrega=_d(2026, 9, 19, 18, 30), tardia=0, nota=D("16.50"), aprobado=None,
                 comentario_docente="Muy bien", calificado_at=_d(2026, 9, 21, 10, 0), created_at=_d(2026, 9, 19, 18, 30),
                 retro_ruta="2026/09/retro.jpg", retro_nombre="corregida.jpg"),
            dict(id=3001, tarea_id=2000, alumno_id=11, archivo_ruta=None, archivo_nombre=None, enlace="https://ejemplo.pe/mi-hoja",
                 comentario_alumno=None, fecha_entrega=_d(2026, 9, 22, 8, 0), tardia=1, nota=None, aprobado=None,
                 comentario_docente=None, calificado_at=None, created_at=_d(2026, 9, 22, 8, 0), retro_ruta=None, retro_nombre=None),
            dict(id=3002, tarea_id=2000, alumno_id=21, archivo_ruta=None, archivo_nombre=None, enlace=None, comentario_alumno=None,
                 fecha_entrega=t0, tardia=0, nota=None, aprobado=None, comentario_docente=None, calificado_at=None, created_at=t0,
                 retro_ruta=None, retro_nombre=None),
            dict(id=3003, tarea_id=2001, alumno_id=10, archivo_ruta=None, archivo_nombre=None, enlace=None, comentario_alumno=None,
                 fecha_entrega=_d(2026, 9, 24, 9, 0), tardia=0, nota=None, aprobado=1, comentario_docente=None,
                 calificado_at=_d(2026, 9, 26, 9, 0), created_at=_d(2026, 9, 24, 9, 0), retro_ruta=None, retro_nombre=None),
        ],  # fmt: skip
        "av_sesiones": [
            dict(id=4000, curso_id=3, fecha=date(2026, 9, 2), tema="Introducción", created_at=t0),
            dict(id=4001, curso_id=8, fecha=date(2026, 9, 2), tema=None, created_at=t0),
        ],
        "av_asistencias": [
            dict(id=5000, sesion_id=4000, alumno_id=10, estado="presente", observacion=None, created_at=t0),
            dict(id=5001, sesion_id=4000, alumno_id=11, estado="falta", observacion="Avisó que estaba enfermo", created_at=t0),
            dict(id=5002, sesion_id=4000, alumno_id=21, estado="tarde", observacion=None, created_at=t0),
        ],
        "av_anuncios": [
            dict(id=6000, curso_id=3, autor_id=5, titulo="Bienvenidos", contenido="Mañana traer peine y tijera.", created_at=_d(2026, 9, 1, 10, 0)),
            dict(id=6001, curso_id=3, autor_id=20, titulo="Aviso de prueba", contenido="…", created_at=t0),
        ],
        "av_preguntas_clase": [
            dict(id=7000, unidad_id=100, autor_id=10, padre_id=None, texto="¿Se puede usar otra capa?", created_at=_d(2026, 9, 3, 9, 0)),
            dict(id=7001, unidad_id=100, autor_id=5, padre_id=7000, texto="Sí, una limpia.", created_at=_d(2026, 9, 3, 9, 30)),
            dict(id=7002, unidad_id=100, autor_id=21, padre_id=None, texto="Pregunta de prueba", created_at=t0),
            dict(id=7003, unidad_id=100, autor_id=5, padre_id=7002, texto="Respuesta a la prueba", created_at=t0),
        ],
        "av_notificaciones": [
            dict(id=8000, usuario_id=10, mensaje="Tienes una tarea nueva", enlace="/tareas/2000", leida=0, created_at=_d(2026, 9, 5, 9, 0)),
            dict(id=8001, usuario_id=21, mensaje="Aviso de prueba", enlace=None, leida=1, created_at=t0),
        ],
        "av_conversaciones": [
            dict(id=9000, curso_id=3, docente_id=5, alumno_id=10, updated_at=_d(2026, 9, 6, 11, 0), created_at=_d(2026, 9, 6, 10, 0)),
            dict(id=9001, curso_id=3, docente_id=5, alumno_id=21, updated_at=t0, created_at=t0),
        ],
        "av_mensajes": [
            dict(id=9500, conversacion_id=9000, autor_id=10, texto="Hola profe", leido_at=None, archivo_ruta=None,
                 archivo_nombre=None, created_at=_d(2026, 9, 6, 10, 0)),
            dict(id=9501, conversacion_id=9000, autor_id=5, texto="Hola, dime", leido_at=_d(2026, 9, 6, 11, 5),
                 archivo_ruta="2026/09/msg.png", archivo_nombre="foto.png", created_at=_d(2026, 9, 6, 11, 0)),
            dict(id=9502, conversacion_id=9001, autor_id=21, texto="Mensaje de prueba", leido_at=None, archivo_ruta=None,
                 archivo_nombre=None, created_at=t0),
        ],  # fmt: skip
        "av_cuestionarios": [
            dict(id=10, unidad_id=100, modo="examen", titulo="Examen de higiene", instrucciones="Lee con calma.", mensaje_final="¡Gracias!",
                 fecha_inicio=None, fecha_limite=_d(2026, 9, 30, 23, 59), tiempo_minutos=15, intentos_max=2, mezclar=1,
                 mostrar_respuestas=1, publicado=1, created_at=t0, eliminado_at=None),
            dict(id=11, unidad_id=101, modo="encuesta", titulo="Encuesta del taller", instrucciones=None, mensaje_final=None,
                 fecha_inicio=_d(2026, 9, 10, 8, 0), fecha_limite=_d(2026, 10, 10, 23, 59), tiempo_minutos=None, intentos_max=1,
                 mezclar=0, mostrar_respuestas=0, publicado=0, created_at=t0, eliminado_at=_d(2026, 10, 2, 9, 0)),
            dict(id=12, unidad_id=103, modo="trabajo", titulo="Formulario de prueba", instrucciones=None, mensaje_final=None,
                 fecha_inicio=None, fecha_limite=_d(2026, 10, 10, 23, 59), tiempo_minutos=None, intentos_max=1, mezclar=0,
                 mostrar_respuestas=1, publicado=1, created_at=t0, eliminado_at=None),
        ],  # fmt: skip
        "av_preguntas": [
            dict(id=40, cuestionario_id=10, tipo="opcion", enunciado="¿Qué desinfecta la tijera?", ayuda="Elige una", imagen_ruta=None,
                 obligatoria=1, puntos=D("2.00"), respuestas_aceptadas=None, explicacion="El alcohol", permite_otra=0,
                 escala_min=None, escala_max=None, etiqueta_min=None, etiqueta_max=None, orden=1),
            dict(id=41, cuestionario_id=10, tipo="vf", enunciado="Se desinfecta después de cada cliente.", ayuda=None,
                 imagen_ruta=None, obligatoria=1, puntos=D("1.00"), respuestas_aceptadas=None, explicacion=None, permite_otra=0,
                 escala_min=None, escala_max=None, etiqueta_min=None, etiqueta_max=None, orden=2),
            dict(id=42, cuestionario_id=10, tipo="cuadricula", enunciado="Relaciona", ayuda=None, imagen_ruta=None, obligatoria=0,
                 puntos=D("0.00"), respuestas_aceptadas=None, explicacion=None, permite_otra=0, escala_min=None, escala_max=None,
                 etiqueta_min=None, etiqueta_max=None, orden=3),
            dict(id=43, cuestionario_id=11, tipo="escala", enunciado="¿Qué tal el taller?", ayuda=None, imagen_ruta="2026/09/preg.png",
                 obligatoria=1, puntos=D("0.00"), respuestas_aceptadas=None, explicacion=None, permite_otra=0, escala_min=1,
                 escala_max=5, etiqueta_min="Mal", etiqueta_max="Muy bien", orden=1),
            dict(id=44, cuestionario_id=12, tipo="abierta", enunciado="Pregunta de prueba", ayuda=None, imagen_ruta=None,
                 obligatoria=1, puntos=D("1.00"), respuestas_aceptadas=None, explicacion=None, permite_otra=0, escala_min=None,
                 escala_max=None, etiqueta_min=None, etiqueta_max=None, orden=1),
        ],  # fmt: skip
        "av_opciones": [
            dict(id=400, pregunta_id=40, grupo="opcion", texto="Alcohol", correcta=1, orden=1),
            dict(id=401, pregunta_id=40, grupo="opcion", texto="Agua", correcta=0, orden=2),
            dict(id=402, pregunta_id=41, grupo="opcion", texto="Verdadero", correcta=1, orden=1),
            dict(id=403, pregunta_id=41, grupo="opcion", texto="Falso", correcta=0, orden=2),
            dict(id=404, pregunta_id=42, grupo="fila", texto="Tijera", correcta=0, orden=1),
            dict(id=405, pregunta_id=42, grupo="columna", texto="Alcohol", correcta=0, orden=1),
            dict(id=406, pregunta_id=44, grupo="opcion", texto="Opción de prueba", correcta=0, orden=1),
        ],
        "av_intentos": [
            dict(id=50, cuestionario_id=10, alumno_id=10, inicio=_d(2026, 9, 10, 10, 0), fin=_d(2026, 9, 10, 10, 12), fuera_tiempo=0,
                 puntaje=D("3.00"), puntaje_max=D("3.00"), nota=D("20.00"), revisado=1, comentario="Excelente"),
            dict(id=51, cuestionario_id=10, alumno_id=11, inicio=_d(2026, 9, 11, 10, 0), fin=None, fuera_tiempo=0, puntaje=None,
                 puntaje_max=None, nota=None, revisado=0, comentario=None),
            dict(id=52, cuestionario_id=10, alumno_id=21, inicio=t0, fin=None, fuera_tiempo=0, puntaje=None, puntaje_max=None,
                 nota=None, revisado=0, comentario=None),
        ],  # fmt: skip
        "av_respuestas": [
            dict(id=60, intento_id=50, pregunta_id=40, opciones="400", texto=None, archivo_ruta=None, archivo_nombre=None,
                 puntos=D("2.00"), comentario=None),
            dict(id=61, intento_id=50, pregunta_id=41, opciones="402", texto=None, archivo_ruta=None, archivo_nombre=None,
                 puntos=D("1.00"), comentario=None),
            dict(id=62, intento_id=50, pregunta_id=42, opciones=None, texto='{"404":"405"}', archivo_ruta="2026/09/resp.pdf",
                 archivo_nombre="resp.pdf", puntos=None, comentario="Revisar"),
            dict(id=63, intento_id=51, pregunta_id=40, opciones="401", texto=None, archivo_ruta=None, archivo_nombre=None,
                 puntos=D("0.00"), comentario=None),
            dict(id=64, intento_id=52, pregunta_id=44, opciones=None, texto="Respuesta de prueba", archivo_ruta=None,
                 archivo_nombre=None, puntos=None, comentario=None),
        ],  # fmt: skip
        "av_registro": [
            dict(id=70, usuario_id=5, accion="acceso", detalle="Entró al aula", ip="190.1.2.3", created_at=_d(2026, 9, 1, 7, 0)),
            dict(id=71, usuario_id=21, accion="acceso", detalle="Entró (prueba)", ip=None, created_at=_d(2026, 9, 1, 7, 5)),
            dict(id=72, usuario_id=None, accion="ajustes", detalle="Se cambiaron los colores", ip="", created_at=_d(2026, 9, 2, 7, 5)),
        ],
        "av_configuracion": [
            dict(clave="color_primario", valor="#0b5cab", updated_at=_d(2026, 9, 3, 15, 0)),
            dict(clave="logo", valor="2026/09/logo.png", updated_at=_d(2026, 9, 3, 15, 5)),
            dict(clave="nombre_cetpro", valor="CETPRO Mangomarca", updated_at=_d(2026, 9, 3, 15, 10)),
        ],
        "av_accesos": [
            dict(id=1, clave="login:71234567", created_at=_d(2026, 9, 4, 8, 0)),
            dict(id=2, clave="login:71234567", created_at=_d(2026, 9, 4, 8, 1)),
            dict(id=3, clave="codigo:ip:1.2.3.4", created_at=_d(2026, 9, 4, 8, 2)),
        ],
        "av_asistente_logs": [
            dict(id=1, usuario_id=5, pedido="¿Qué tareas hay?", herramienta="listar_tareas", respuesta="…", created_at=_d(2026, 9, 5, 8, 0)),
            dict(id=2, usuario_id=10, pedido="Hola", herramienta=None, respuesta="Hola", created_at=_d(2026, 9, 5, 8, 5)),
        ],
    }  # fmt: skip
