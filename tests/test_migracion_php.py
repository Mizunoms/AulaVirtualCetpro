"""Pasar los datos del sistema anterior (PHP + MariaDB) a este: personas, módulos, notas, formularios, archivos y contraseñas."""

import copy
import importlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.academico.models import Aviso, Clase, Evaluacion, Matricula, Modulo, PreguntaClase, UnidadDidactica
from apps.cuentas.models import Origen, Preferencia, Rol, Usuario
from apps.evaluacion.models import Asistencia, SesionAsistencia
from apps.formularios.models import Formulario, Intento, Opcion, Pregunta, Respuesta
from apps.mensajes.models import Conversacion, Mensaje
from apps.nucleo.migracion_php import COLUMNAS, MigracionError, Migrador, OrigenMemoria, clave_django
from apps.nucleo.models import Ajuste, Notificacion, Registro
from apps.tareas.models import Entrega, Material, Tarea

from .migracion_datos import CLAVES, datos_origen

pytestmark = pytest.mark.django_db


def migrar(datos=None, **opciones):
    informe = Migrador(OrigenMemoria(datos if datos is not None else datos_origen()), **opciones).correr()
    return informe


def lima(*partes):
    """Una hora de Lima como la verá la base nueva (en UTC)."""
    return datetime(*partes, tzinfo=ZoneInfo("America/Lima")).astimezone(UTC)


@pytest.fixture
def pasado():
    return migrar()


# ===================================================================== Personas


def test_las_personas_conservan_sus_numeros_y_las_de_prueba_no_pasan(pasado):
    assert sorted(Usuario.objects.values_list("id", flat=True)) == [1, 2, 5, 7, 10, 11, 12]
    assert not Usuario.objects.filter(correo__endswith="@prueba.local").exists()
    assert pasado.omitidas["usuarios"] == {"cuenta del antiguo modo prueba": 2}


def test_datos_de_cada_persona(pasado):
    admin = Usuario.objects.get(pk=1)
    assert admin.correo == "admin@cetpro.test"  # en minúsculas
    assert admin.rol == Rol.ADMIN and admin.is_staff and admin.is_superuser and admin.telefono == ""
    direccion = Usuario.objects.get(pk=2)
    assert direccion.rol == Rol.DIRECCION and not direccion.is_staff and direccion.dni is None

    ana = Usuario.objects.get(pk=10)
    assert (ana.dni, ana.nombre_completo, ana.telefono) == ("71234567", "Ana María Quispe Rojas", "987654321")
    assert ana.correo is None and ana.fecha_nacimiento == date(1990, 5, 17) and ana.origen == Origen.REGISTRO
    assert ana.activado == lima(2026, 9, 1, 8, 30) and ana.creado == lima(2026, 9, 1, 8, 0)
    assert ana.is_active and not ana.debe_cambiar_clave


def test_alumno_sin_contrasena_sigue_pendiente_y_el_inactivo_sigue_inactivo(pasado):
    luis = Usuario.objects.get(pk=11)
    assert luis.pendiente and luis.correo is None and luis.origen == Origen.LISTA  # correo "" → ninguno
    eva = Usuario.objects.get(pk=12)
    assert not eva.is_active and eva.debe_cambiar_clave
    assert Usuario.objects.get(pk=5).debe_cambiar_clave  # el docente aún debía elegir su contraseña


def test_las_preferencias_pasan_y_las_de_cuentas_de_prueba_no(pasado):
    p = Preferencia.objects.get()
    assert (p.usuario_id, p.tamano_letra, p.alto_contraste, p.lectura_voz, p.modo_asistente) == (10, "grande", True, True, "voz")
    assert p.actualizado == lima(2026, 9, 2, 10, 0)


# ===================================================================== Contraseñas


def test_clave_django_convierte_bcrypt_de_php():
    assert clave_django("$2y$10$" + "a" * 53) == "bcrypt$$2b$10$" + "a" * 53
    assert not Usuario(password=clave_django("")).has_usable_password()
    assert not Usuario(password=clave_django("no-es-bcrypt")).has_usable_password()


def test_las_contrasenas_de_php_siguen_sirviendo_y_se_vuelven_a_guardar(client, settings):
    # En las pruebas los hashers son rápidos (MD5); aquí se usan los de verdad.
    settings.PASSWORD_HASHERS = importlib.import_module("config.settings").PASSWORD_HASHERS
    migrar()
    ana = Usuario.objects.get(pk=10)
    assert ana.password.startswith("bcrypt$$2b$")
    assert not ana.check_password("otra-cosa")
    assert ana.check_password(CLAVES["ana"])
    ana.refresh_from_db()
    assert ana.password.startswith("pbkdf2_sha256$")  # al entrar se guarda con el hasher de Django

    r = client.post(reverse("cuentas:login"), {"usuario": "71234567", "clave": CLAVES["ana"], "tipo": "alumno"})
    assert r.status_code == 302 and r["Location"] == reverse("nucleo:inicio")
    client.logout()
    r = client.post(reverse("cuentas:login"), {"usuario": "rosa@cetpro.test", "clave": CLAVES["rosa"], "tipo": "personal"})
    assert r.status_code == 302 and Usuario.objects.get(pk=5).password.startswith("pbkdf2_sha256$")


# ===================================================================== Módulos


def test_modulos_con_su_codigo_y_los_de_cuentas_de_prueba_no_pasan(pasado):
    assert sorted(Modulo.objects.values_list("id", flat=True)) == [3, 4]
    pelu = Modulo.objects.get(pk=3)
    assert (pelu.nombre, pelu.especialidad, pelu.modulo, pelu.turno, pelu.docente_id) == (
        "Peluquería – Módulo I", "Peluquería y Barbería", "Módulo I", "mañana", 5
    )  # fmt: skip
    assert pelu.codigo == "PEL4821" and pelu.inscripcion_abierta and pelu.whatsapp_grupo.endswith("grupo-pelu")
    pan = Modulo.objects.get(pk=4)
    assert not pan.activo and pan.modulo == "" and pan.horario == ""
    assert re.fullmatch(r"PAN\d{4}", pan.codigo)  # no tenía código: recibió uno
    assert pelu.creado == lima(2026, 9, 1, 7, 0)


def test_matriculas_unidades_didacticas_y_evaluacion(pasado):
    assert sorted(Matricula.objects.values_list("id", "modulo_id", "alumno_id")) == [
        (1, 3, 10),
        (2, 3, 11),
        (3, 3, 12),
        (4, 4, 10),
    ]
    assert list(UnidadDidactica.objects.order_by("orden").values_list("nombre", "creditos", "horas")) == [
        ("Corte básico", 3, 48), ("Tinte", None, None)
    ]  # fmt: skip
    ev = Evaluacion.objects.get()
    assert (ev.modulo_id, ev.peso_tareas, ev.peso_tests, ev.peso_asistencia, ev.nota_minima) == (3, 40, 40, 20, Decimal("12.00"))


# ===================================================================== Clases, materiales, tareas y entregas


def test_clases_y_materiales(pasado):
    c = Clase.objects.get(pk=100)
    assert (c.modulo_id, c.titulo, c.visible, c.estado) == (3, "Clase 1 – Higiene", True, "auto")
    assert (c.fecha_inicio, c.fecha_fin) == (date(2026, 9, 1), date(2026, 9, 30))
    c2 = Clase.objects.get(pk=101)
    assert not c2.visible and c2.estado == "cerrada" and c2.descripcion == ""
    assert sorted(Clase.objects.values_list("id", flat=True)) == [100, 101, 102]

    m = Material.objects.get(pk=1000)
    assert (m.clase_id, m.tipo, m.archivo_ruta, m.archivo_nombre, m.url) == (100, "archivo", "2026/09/aaaa.pdf", "Guía.pdf", "")
    papelera = Material.todos.get(pk=1002)
    assert papelera.eliminado == lima(2026, 10, 1, 12, 0)
    assert not Material.objects.filter(pk=1002).exists()  # sigue en la papelera, no en la lista


def test_tareas_y_entregas_con_sus_notas(pasado):
    t = Tarea.objects.get(pk=2000)
    assert t.fecha_limite == lima(2026, 9, 20, 23, 59)
    assert (t.politica_tardia, t.penalidad_puntos, t.tipo_calificacion, t.puntaje_max) == (
        "penalidad",
        Decimal("2"),
        "nota",
        Decimal("20"),
    )
    r = Tarea.objects.get(pk=2001)
    assert (r.tipo, r.tipo_calificacion, r.criterios) == ("grupal", "rubrica", "Limpieza|5\nPrecisión|5")
    assert not Tarea.todos.filter(pk=2002).exists()  # era de un módulo de prueba

    e = Entrega.objects.get(pk=3000)
    assert (e.tarea_id, e.alumno_id, e.nota, e.aprobado, e.tardia) == (2000, 10, Decimal("16.50"), None, False)
    assert (e.comentario_alumno, e.comentario_docente, e.retro_ruta) == ("Aquí está", "Muy bien", "2026/09/retro.jpg")
    assert e.fecha_entrega == lima(2026, 9, 19, 18, 30) and e.calificado == lima(2026, 9, 21, 10, 0)
    tarde = Entrega.objects.get(pk=3001)
    assert tarde.tardia and tarde.nota is None and tarde.calificado is None and tarde.enlace.endswith("mi-hoja")
    assert Entrega.objects.get(pk=3003).aprobado is True
    assert sorted(Entrega.objects.values_list("id", flat=True)) == [3000, 3001, 3003]


# ===================================================================== Asistencia, avisos, preguntas, notificaciones y mensajes


def test_asistencia_y_avisos(pasado):
    s = SesionAsistencia.objects.get()
    assert (s.pk, s.modulo_id, s.fecha, s.tema) == (4000, 3, date(2026, 9, 2), "Introducción")
    assert sorted(Asistencia.objects.values_list("alumno_id", "estado")) == [(10, "presente"), (11, "falta")]
    assert Asistencia.objects.get(alumno_id=11).observacion == "Avisó que estaba enfermo"
    a = Aviso.objects.get()
    assert (a.pk, a.autor_id, a.titulo) == (6000, 5, "Bienvenidos") and a.creado == lima(2026, 9, 1, 10, 0)


def test_preguntas_de_la_clase_y_sus_respuestas(pasado):
    assert sorted(PreguntaClase.objects.values_list("id", "padre_id")) == [(7000, None), (7001, 7000)]
    assert pasado.omitidas["av_preguntas_clase"] == {
        "depende de usuarios que no se pasó": 1,
        "responde a una pregunta que no se pasó": 1,
    }  # la pregunta de una cuenta de prueba y la respuesta que le habían dado


def test_notificaciones_conservan_su_fecha(pasado):
    n = Notificacion.objects.get()
    assert (n.pk, n.usuario_id, n.leida, n.enlace) == (8000, 10, False, "/tareas/2000")
    assert n.creado == lima(2026, 9, 5, 9, 0)  # no la de hoy


def test_mensajes_con_sus_adjuntos(pasado):
    c = Conversacion.objects.get()
    assert (c.pk, c.modulo_id, c.docente_id, c.alumno_id) == (9000, 3, 5, 10) and c.actualizado == lima(2026, 9, 6, 11, 0)
    sin_leer, leido = Mensaje.objects.order_by("id")
    assert sin_leer.leido is None and sin_leer.archivo_ruta == ""
    assert leido.leido == lima(2026, 9, 6, 11, 5) and (leido.archivo_ruta, leido.archivo_nombre) == (
        "2026/09/msg.png",
        "foto.png",
    )


# ===================================================================== Formularios


def test_formularios_con_preguntas_alternativas_e_intentos(pasado):
    f = Formulario.todos.get(pk=10)
    assert (f.clase_id, f.modo, f.publicado, f.tiempo_minutos, f.intentos_max, f.mezclar) == (100, "examen", True, 15, 2, True)
    assert f.fecha_inicio is None and f.fecha_limite == lima(2026, 9, 30, 23, 59) and f.mensaje_final == "¡Gracias!"
    encuesta = Formulario.todos.get(pk=11)
    assert encuesta.modo == "encuesta" and encuesta.eliminado == lima(2026, 10, 2, 9, 0)
    assert encuesta.fecha_inicio == lima(2026, 9, 10, 8, 0)
    assert not Formulario.todos.filter(pk=12).exists()

    assert sorted(Pregunta.objects.values_list("id", "formulario_id", "tipo")) == [
        (40, 10, "opcion"), (41, 10, "vf"), (42, 10, "cuadricula"), (43, 11, "escala")
    ]  # fmt: skip
    escala = Pregunta.objects.get(pk=43)
    assert (escala.escala_min, escala.escala_max, escala.etiqueta_max, escala.imagen_ruta) == (
        1,
        5,
        "Muy bien",
        "2026/09/preg.png",
    )
    assert Pregunta.objects.get(pk=40).puntos == Decimal("2.00") and Pregunta.objects.get(pk=40).explicacion == "El alcohol"
    assert sorted(Opcion.objects.values_list("id", "pregunta_id", "grupo", "correcta")) == [
        (400, 40, "opcion", True), (401, 40, "opcion", False), (402, 41, "opcion", True), (403, 41, "opcion", False),
        (404, 42, "fila", False), (405, 42, "columna", False),
    ]  # fmt: skip


def test_las_respuestas_siguen_apuntando_a_sus_alternativas(pasado):
    i = Intento.objects.get(pk=50)
    assert (i.formulario_id, i.alumno_id, i.nota, i.revisado, i.comentario) == (10, 10, Decimal("20.00"), True, "Excelente")
    assert i.inicio == lima(2026, 9, 10, 10, 0) and i.fin == lima(2026, 9, 10, 10, 12)
    assert Intento.objects.get(pk=51).fin is None
    assert not Intento.objects.filter(pk=52).exists()

    marcada = Respuesta.objects.get(pk=60)
    assert marcada.opciones == "400" and Opcion.objects.get(pk=int(marcada.opciones)).texto == "Alcohol"
    assert marcada.puntos == Decimal("2.00")
    cuadricula = Respuesta.objects.get(pk=62)
    assert cuadricula.texto == '{"404":"405"}' and cuadricula.puntos is None  # falta revisar: sigue pendiente
    assert (cuadricula.archivo_ruta, cuadricula.comentario) == ("2026/09/resp.pdf", "Revisar")
    assert sorted(Respuesta.objects.values_list("id", flat=True)) == [60, 61, 62, 63]


# ===================================================================== Registro y ajustes


def test_registro_de_actividad_y_ajustes_conservan_sus_fechas(pasado):
    assert sorted(Registro.objects.values_list("id", flat=True)) == [70, 71, 72, 73]
    assert Registro.objects.get(pk=73).detalle.startswith("Se pasaron los datos")  # la propia migración queda anotada
    r70, r71, r72 = (Registro.objects.get(pk=p) for p in (70, 71, 72))
    assert r70.usuario_id == 5 and r70.creado == lima(2026, 9, 1, 7, 0) and r70.ip == "190.1.2.3"
    assert r71.usuario is None and r71.detalle == "Entró (prueba)"  # la cuenta de prueba no pasó; el registro se queda
    assert r72.usuario is None and r72.ip == ""
    assert dict(Ajuste.objects.values_list("clave", "valor")) == {
        "color_primario": "#0b5cab", "logo": "2026/09/logo.png", "nombre_cetpro": "CETPRO Mangomarca"
    }  # fmt: skip
    assert Ajuste.objects.get(clave="logo").actualizado == lima(2026, 9, 3, 15, 5)


def test_lo_que_no_se_pasa_se_cuenta_y_se_avisa(pasado):
    assert pasado.no_pasadas["av_accesos"][0] == 3 and pasado.no_pasadas["av_asistente_logs"][0] == 2
    texto = pasado.texto()
    assert "av_accesos: 3" in texto and "cuenta del antiguo modo prueba" in texto and "Migración terminada" in texto


def test_despues_de_pasar_los_numeros_nuevos_siguen_adelante(pasado):
    nuevo = Usuario.objects.create_user(correo="nuevo@cetpro.test", nombres="Nuevo", rol=Rol.DOCENTE)
    assert nuevo.pk > 12
    tarea = Tarea.objects.create(clase_id=100, titulo="Nueva", fecha_limite=datetime(2026, 12, 1, tzinfo=UTC))
    assert tarea.pk > 2001
    assert Modulo.crear(nombre="Otro", especialidad="Soldadura", periodo="2026-II", turno="noche", docente=nuevo).pk > 4


# ===================================================================== Ensayo, cuentas de prueba y errores


def test_ensayo_cuenta_todo_y_no_guarda_nada():
    informe = migrar(solo_revisar=True)
    assert informe.importadas["usuarios"] == 7 and informe.importadas["cursos"] == 2
    assert not Usuario.objects.exists() and not Modulo.objects.exists() and not Respuesta.objects.exists()
    assert "ENSAYO" in informe.texto()


def test_con_cuentas_de_prueba_pasan_desactivadas():
    migrar(con_cuentas_de_prueba=True)
    assert Usuario.objects.count() == 9
    assert not Usuario.objects.get(pk=20).is_active and not Usuario.objects.get(pk=21).is_active
    assert Modulo.objects.filter(pk=8).exists() and Tarea.todos.filter(pk=2002).exists()


def test_no_se_migra_sobre_una_base_con_personas(docente):
    with pytest.raises(MigracionError, match="ya tiene personas"):
        migrar()
    assert Usuario.objects.count() == 1


def test_base_anterior_sin_tablas_o_columnas_nuevas_pide_actualizarla():
    with pytest.raises(MigracionError, match="av_unidades_didacticas") as e:
        Migrador(OrigenMemoria(datos_origen(), sin_tablas=["av_unidades_didacticas"])).correr()
    assert "migrar.php" in str(e.value)
    with pytest.raises(MigracionError, match=r"av_entregas\.retro_ruta"):
        Migrador(OrigenMemoria(datos_origen(), sin_columnas=[("av_entregas", "retro_ruta")])).correr()
    assert not Usuario.objects.exists()  # no se tocó nada


def test_una_fila_que_falla_deshace_todo():
    datos = datos_origen()
    datos["usuarios"].append(dict(datos["usuarios"][2], id=99))  # mismo DNI y correo que Rosa: choca
    with pytest.raises(MigracionError, match="No se guardó nada"):
        migrar(datos)
    assert not Usuario.objects.exists() and not Modulo.objects.exists()


def test_valores_raros_se_cambian_por_uno_valido_y_se_avisa():
    datos = copy.deepcopy(datos_origen())
    datos["av_tareas"][0]["politica_tardia"] = "rara"
    datos["cursos"][0]["nombre"] = "N" * 200
    informe = migrar(datos)
    assert Tarea.objects.get(pk=2000).politica_tardia == "no_acepta"
    assert Modulo.objects.get(pk=3).nombre == "N" * 150
    assert any("rara" in a for a in informe.avisos) and any("cursos #3" in a and "150" in a for a in informe.avisos)


def test_el_comando_avisa_si_no_puede_conectarse_a_la_base_anterior():
    with pytest.raises(CommandError, match="No pude conectarme"):
        call_command("migrar_desde_php", puerto=1, base="no_existe")


def test_todas_las_tablas_que_se_leen_tienen_datos_de_ejemplo():
    # Si el sistema anterior suma una tabla, hay que sumarla aquí y en la migración.
    assert set(COLUMNAS) <= set(datos_origen())


# ===================================================================== Archivos subidos


@pytest.fixture
def carpeta_vieja(tmp_path):
    vieja = tmp_path / "vieja"
    for ruta in ("2026/09/aaaa.pdf", "2026/09/ent.jpg", "2026/09/logo.png", "2026/09/msg.png"):
        archivo = vieja / ruta
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(b"contenido " + ruta.encode())
    (tmp_path / "fuera.txt").write_text("secreto")  # al lado de la carpeta: no debe copiarse
    return vieja


def test_los_archivos_se_copian_con_el_mismo_nombre(settings, carpeta_vieja):
    informe = migrar(carpeta_archivos=carpeta_vieja)
    nueva = settings.MEDIA_ROOT
    assert (nueva / "2026/09/aaaa.pdf").read_bytes() == b"contenido 2026/09/aaaa.pdf"
    assert (nueva / "2026/09/logo.png").exists() and (nueva / "2026/09/msg.png").exists() and (nueva / "2026/09/ent.jpg").exists()
    assert informe.archivos_copiados == 4
    assert "2026/09/tarea.pdf" in informe.archivos_faltan  # tiene registro pero el archivo no está
    assert not list(nueva.rglob("fuera.txt"))  # el archivo de afuera no se copia
    assert any("../fuera.txt" in a for a in informe.avisos)
    assert "4 copiados" in informe.texto()


def test_el_ensayo_no_copia_archivos(settings, carpeta_vieja):
    informe = migrar(carpeta_archivos=carpeta_vieja, solo_revisar=True)
    assert informe.archivos_copiados == 4 and not settings.MEDIA_ROOT.exists()
    assert "4 se copiarían" in informe.texto()


def test_no_pisa_un_archivo_que_ya_esta(settings, carpeta_vieja):
    ya = settings.MEDIA_ROOT / "2026/09/aaaa.pdf"
    ya.parent.mkdir(parents=True)
    ya.write_bytes(b"el que ya estaba")
    informe = migrar(carpeta_archivos=carpeta_vieja)
    assert ya.read_bytes() == b"el que ya estaba" and informe.archivos_ya_estaban == 1 and informe.archivos_copiados == 3


def test_carpeta_de_archivos_que_no_existe(tmp_path):
    with pytest.raises(MigracionError, match="carpeta de archivos"):
        migrar(carpeta_archivos=tmp_path / "no-hay")
