"""Pasa los datos del sistema anterior (PHP + MariaDB) a este (Django + PostgreSQL).

Qué hace:
- Lee la base anterior SIN modificarla (solo SELECT) y escribe en la base nueva, que debe estar vacía (sin personas).
- Conserva los mismos números (id) de personas, módulos, clases, tareas, notas… así los enlaces y las alturas de la base
  siguen igual, y las respuestas de los formularios siguen apuntando a sus alternativas.
- Las contraseñas bcrypt (`$2y$…`) pasan tal cual: siguen sirviendo y se vuelven a guardar con el hasher de Django al entrar.
- Copia los archivos subidos (fotos, trabajos, materiales) con el mismo nombre, solo los que tienen un registro.
- Todo ocurre en una sola transacción: si algo falla, la base nueva queda como estaba. «Solo revisar» hace todo y deshace.

Qué NO pasa (a propósito): las cuentas del antiguo «modo prueba» (salvo que se pida), los intentos fallidos de entrar
(`av_accesos`), el historial del asistente (`av_asistente_logs`) y las migraciones aplicadas (`av_migraciones`).
"""

from __future__ import annotations

import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.color import no_style
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.academico.models import (
    Aviso,
    Clase,
    Evaluacion,
    Matricula,
    Modulo,
    PreguntaClase,
    UnidadDidactica,
)
from apps.cuentas.models import Origen, Preferencia, Rol, TamanoLetra, Usuario
from apps.evaluacion.models import Asistencia, Estado, SesionAsistencia
from apps.formularios.models import MODOS, TIPOS, Formulario, Intento, Opcion, Pregunta, Respuesta
from apps.mensajes.models import Conversacion, Mensaje
from apps.nucleo.models import Ajuste, Notificacion, Registro
from apps.tareas.models import (
    Entrega,
    Material,
    PoliticaTardia,
    Tarea,
    TipoCalificacion,
    TipoMaterial,
    TipoTarea,
)

# Tablas del sistema anterior que se leen, con las columnas que se usan (también sirven para comprobar que la base está al día).
COLUMNAS = {
    "usuarios": "id dni nombres apellidos correo telefono password_hash rol activo es_prueba created_at",
    "av_perfiles": "usuario_id fecha_nacimiento origen activado_at cambiar_clave",
    "av_preferencias": "usuario_id tamano_letra alto_contraste lectura_voz modo_asistente updated_at",
    "cursos": "id nombre especialidad modulo periodo turno horario docente_id activo created_at",
    "av_inscripcion": "curso_id codigo abierta whatsapp_grupo",
    "matriculas": "id curso_id alumno_id created_at",
    "av_unidades_didacticas": "id curso_id nombre creditos horas orden",
    "av_evaluacion": "curso_id peso_tareas peso_tests peso_asistencia nota_minima",
    "av_unidades": "id curso_id titulo descripcion orden visible fecha_inicio fecha_fin estado created_at",
    "av_materiales": "id unidad_id titulo descripcion tipo archivo_ruta archivo_nombre url created_at eliminado_at",
    "av_tareas": (
        "id unidad_id titulo instrucciones criterios archivo_ruta archivo_nombre fecha_limite puntaje_max politica_tardia "
        "penalidad_puntos tipo_calificacion tipo created_at eliminado_at"
    ),
    "av_entregas": (
        "id tarea_id alumno_id archivo_ruta archivo_nombre enlace comentario_alumno fecha_entrega tardia nota aprobado "
        "comentario_docente calificado_at created_at retro_ruta retro_nombre"
    ),
    "av_sesiones": "id curso_id fecha tema created_at",
    "av_asistencias": "id sesion_id alumno_id estado observacion created_at",
    "av_anuncios": "id curso_id autor_id titulo contenido created_at",
    "av_preguntas_clase": "id unidad_id autor_id padre_id texto created_at",
    "av_notificaciones": "id usuario_id mensaje enlace leida created_at",
    "av_conversaciones": "id curso_id docente_id alumno_id updated_at created_at",
    "av_mensajes": "id conversacion_id autor_id texto leido_at archivo_ruta archivo_nombre created_at",
    "av_cuestionarios": (
        "id unidad_id modo titulo instrucciones mensaje_final fecha_inicio fecha_limite tiempo_minutos intentos_max mezclar "
        "mostrar_respuestas publicado created_at eliminado_at"
    ),
    "av_preguntas": (
        "id cuestionario_id tipo enunciado ayuda imagen_ruta obligatoria puntos respuestas_aceptadas explicacion permite_otra "
        "escala_min escala_max etiqueta_min etiqueta_max orden"
    ),
    "av_opciones": "id pregunta_id grupo texto correcta orden",
    "av_intentos": "id cuestionario_id alumno_id inicio fin fuera_tiempo puntaje puntaje_max nota revisado comentario",
    "av_respuestas": "id intento_id pregunta_id opciones texto archivo_ruta archivo_nombre puntos comentario",
    "av_registro": "id usuario_id accion detalle ip created_at",
    "av_configuracion": "clave valor updated_at",
}
COLUMNAS = {tabla: tuple(columnas.split()) for tabla, columnas in COLUMNAS.items()}

# Tablas que no se pasan (solo se cuentan, para avisar)
NO_SE_PASAN = {
    "av_accesos": "intentos fallidos de entrar (no sirven)",
    "av_asistente_logs": "historial del asistente (la versión nueva lo hará de nuevo)",
}

# Ajustes del aula cuyo valor es un archivo subido
AJUSTES_CON_ARCHIVO = ("logo", "fondo_login")


class MigracionError(Exception):
    """Mensaje listo para mostrar a la persona que hace la migración."""


# ===================================================================== De dónde se lee


class OrigenMySQL:
    """La base del sistema anterior (MariaDB / MySQL). Solo se hacen SELECT."""

    def __init__(self, host, puerto, usuario, clave, base):
        import pymysql

        self.base = base
        try:
            self.con = pymysql.connect(
                host=host,
                port=puerto,
                user=usuario,
                password=clave,
                database=base,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                read_timeout=300,
            )
        except pymysql.MySQLError as e:
            raise MigracionError(
                f"No pude conectarme a la base «{base}» en {host}:{puerto} con el usuario «{usuario}»: {e}\n"
                "Revisa que MySQL (XAMPP) esté encendido y que los datos de conexión sean los de src/config/config.php."
            ) from e
        try:
            with self.con.cursor() as c:
                c.execute("SET SESSION TRANSACTION READ ONLY")  # por seguridad: esta conexión no puede escribir
        except pymysql.MySQLError:
            pass

    def _consultar(self, sql, params=()):
        with self.con.cursor() as c:
            c.execute(sql, params)
            return list(c.fetchall())

    def tablas(self):
        filas = self._consultar("SELECT table_name AS t FROM information_schema.tables WHERE table_schema = %s", (self.base,))
        return {f["t"] for f in filas}

    def columnas(self, tabla):
        filas = self._consultar(
            "SELECT column_name AS c FROM information_schema.columns WHERE table_schema = %s AND table_name = %s",
            (self.base, tabla),
        )
        return {f["c"] for f in filas}

    def filas(self, tabla, columnas):
        # Los nombres salen de COLUMNAS (no de la persona), por eso se pueden poner directo en la consulta.
        return self._consultar(f"SELECT {', '.join(columnas)} FROM {tabla} ORDER BY 1")  # noqa: S608

    def contar(self, tabla):
        return self._consultar(f"SELECT COUNT(*) AS n FROM {tabla}")[0]["n"]  # noqa: S608

    def cerrar(self):
        self.con.close()


class OrigenMemoria:
    """Datos en memoria con la forma de la base anterior (para las pruebas): {tabla: [fila, …]}."""

    def __init__(self, datos, sin_tablas=(), sin_columnas=()):
        self.datos = datos
        self.sin_tablas = set(sin_tablas)
        self.sin_columnas = set(sin_columnas)

    def tablas(self):
        return (set(COLUMNAS) | set(NO_SE_PASAN) | set(self.datos)) - self.sin_tablas

    def columnas(self, tabla):
        return {c for c in COLUMNAS.get(tabla, ()) if (tabla, c) not in self.sin_columnas}

    def filas(self, tabla, columnas):
        return [{c: f.get(c) for c in columnas} for f in self.datos.get(tabla, [])]

    def contar(self, tabla):
        return len(self.datos.get(tabla, []))

    def cerrar(self):
        pass


# ===================================================================== Qué pasó


@dataclass
class Informe:
    solo_revisar: bool = False
    leidas: dict = field(default_factory=dict)
    importadas: dict = field(default_factory=dict)
    omitidas: dict = field(default_factory=dict)  # tabla -> {motivo: cantidad}
    avisos: list = field(default_factory=list)
    no_pasadas: dict = field(default_factory=dict)
    archivos_copiados: int = 0
    archivos_ya_estaban: int = 0
    archivos_faltan: list = field(default_factory=list)
    archivos_revisados: bool = False

    def omitir(self, tabla, motivo, n=1):
        motivos = self.omitidas.setdefault(tabla, {})
        motivos[motivo] = motivos.get(motivo, 0) + n

    def total_omitidas(self):
        return sum(n for motivos in self.omitidas.values() for n in motivos.values())

    def texto(self):
        lineas = []
        lineas.append(
            "ENSAYO: se hizo todo y se deshizo; no se guardó nada en la base nueva."
            if self.solo_revisar
            else "Migración terminada: los datos ya están en la base nueva."
        )
        lineas.append("")
        lineas.append("Tabla del sistema anterior         leídas  pasadas")
        for tabla, leidas in self.leidas.items():
            lineas.append(f"  {tabla:<30} {leidas:>6}  {self.importadas.get(tabla, 0):>7}")
        if self.omitidas:
            lineas.append("")
            lineas.append("No se pasaron (porque dependen de algo que no se pasó):")
            for tabla, motivos in self.omitidas.items():
                for motivo, n in motivos.items():
                    lineas.append(f"  - {tabla}: {n} ({motivo})")
        if self.no_pasadas:
            lineas.append("")
            lineas.append("No se pasan a propósito:")
            for tabla, (n, para_que) in self.no_pasadas.items():
                lineas.append(f"  - {tabla}: {n} — {para_que}")
        lineas.append("")
        if self.archivos_revisados:
            lineas.append(
                f"Archivos: {self.archivos_copiados} se copiarían, {self.archivos_ya_estaban} ya estaban, "
                f"{len(self.archivos_faltan)} no se encuentran."
                if self.solo_revisar
                else f"Archivos: {self.archivos_copiados} copiados, {self.archivos_ya_estaban} ya estaban, "
                f"{len(self.archivos_faltan)} no se encuentran."
            )
            for ruta in self.archivos_faltan[:15]:
                lineas.append(f"  - falta {ruta}")
            if len(self.archivos_faltan) > 15:
                lineas.append(f"  … y {len(self.archivos_faltan) - 15} más")
        else:
            lineas.append("Archivos: no se indicó la carpeta de archivos del sistema anterior; no se copió ninguno.")
        if self.avisos:
            lineas.append("")
            lineas.append("Avisos:")
            lineas.extend(f"  - {a}" for a in self.avisos)
        return "\n".join(lineas)


# ===================================================================== Pequeñas conversiones


class ClaveDesconocida(Exception):
    """La contraseña guardada no está en un formato que se sepa pasar (no es bcrypt)."""

    def __init__(self, formato):
        super().__init__(formato)
        self.formato = formato


def clave_django(hash_php):
    """Contraseña bcrypt del sistema anterior → formato de Django. Vacía = alumno que aún no creó su contraseña.
    Un formato que no se reconoce NO se trata como «sin contraseña»: así cualquiera podría reclamar la cuenta con el DNI."""
    if not hash_php:
        return make_password(None)
    if hash_php[:4] in ("$2y$", "$2a$", "$2b$") and len(hash_php) == 60:
        return "bcrypt$$2b$" + hash_php[4:]  # $2y$ y $2b$ son el mismo algoritmo
    marca = re.match(r"\$[A-Za-z0-9-]{1,20}\$", hash_php)
    raise ClaveDesconocida(marca.group(0) if marca else "sin formato conocido")


@contextmanager
def _sin_fechas_automaticas(modelo):
    """Deja que los campos `auto_now` / `auto_now_add` guarden la fecha que trae el dato (la de antes), no la de hoy."""
    campos = [f for f in modelo._meta.fields if getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False)]
    guardados = [(f, f.auto_now, f.auto_now_add) for f in campos]
    for f in campos:
        f.auto_now = False
        f.auto_now_add = False
    try:
        yield
    finally:
        for f, auto_now, auto_now_add in guardados:
            f.auto_now = auto_now
            f.auto_now_add = auto_now_add


# ===================================================================== La migración


class Migrador:
    def __init__(
        self,
        origen,
        carpeta_archivos=None,
        zona=None,
        con_cuentas_de_prueba=False,
        desactivar_claves_desconocidas=False,
        solo_revisar=False,
        salida=None,
    ):
        self.origen = origen
        self.carpeta = Path(carpeta_archivos).resolve() if carpeta_archivos else None
        self.zona = ZoneInfo(zona or settings.TIME_ZONE)
        self.con_cuentas_de_prueba = con_cuentas_de_prueba
        self.desactivar_claves_desconocidas = desactivar_claves_desconocidas
        self.claves_desconocidas = []  # (id, rol, formato) de quienes tienen una contraseña que no se sabe pasar
        self.solo_revisar = solo_revisar
        self.salida = salida or (lambda texto: None)
        self.informe = Informe(solo_revisar=solo_revisar)
        self.ids = {}  # tabla del sistema anterior -> conjunto de ids que sí se pasaron
        self.modelos = []  # modelos creados (para reiniciar sus contadores)
        self.rutas = set()  # archivos subidos que quedaron con registro
        self.ahora = timezone.now()

    # ---------------------------------------------------------------- Pasos

    def correr(self):
        self._verificar_origen()
        self._verificar_destino()
        try:
            with transaction.atomic():
                self._importar_todo()
                self._reiniciar_contadores()
                connection.check_constraints()  # que nada quede apuntando a algo que no existe
                if self.solo_revisar:
                    transaction.set_rollback(True)
        except IntegrityError as e:
            raise MigracionError(
                "No se pudo pasar: hay datos que chocan (por ejemplo dos personas con el mismo DNI o correo) o que apuntan a algo "
                "que no existe. No se guardó nada."
                f" Detalle: {e}"
            ) from e
        self._archivos()
        if not self.solo_revisar:
            Registro.anotar(None, "ajustes", "Se pasaron los datos del sistema anterior (PHP) a este.")
        return self.informe

    def _verificar_origen(self):
        tablas = self.origen.tablas()
        faltan_tablas = [t for t in COLUMNAS if t not in tablas]
        if faltan_tablas:
            raise MigracionError(
                "La base del sistema anterior no está al día: le faltan estas tablas: "
                + ", ".join(faltan_tablas)
                + ".\nActualízala primero con «php src/herramientas/migrar.php» (con una copia de seguridad) y vuelve a intentar."
            )
        faltan_columnas = []
        for tabla, columnas in COLUMNAS.items():
            existentes = self.origen.columnas(tabla)
            faltan_columnas += [f"{tabla}.{c}" for c in columnas if c not in existentes]
        if faltan_columnas:
            raise MigracionError(
                "La base del sistema anterior no está al día: le faltan estas columnas: "
                + ", ".join(faltan_columnas)
                + ".\nActualízala primero con «php src/herramientas/migrar.php» (con una copia de seguridad) y vuelve a intentar."
            )

    def _verificar_destino(self):
        if Usuario.objects.exists():
            raise MigracionError(
                "La base nueva ya tiene personas. La migración solo se hace en una base recién creada (después de «migrate» y "
                "sin «createsuperuser»), para no mezclar datos."
            )

    def _importar_todo(self):
        self._perfiles = {f["usuario_id"]: f for f in self._leer("av_perfiles")}
        self._importar_usuarios()
        self._importar_preferencias()
        self._importar_modulos()
        self._importar_clases_y_contenido()
        self._importar_asistencia_y_comunicacion()
        self._importar_formularios()
        self._importar_registro_y_ajustes()
        self._completar_codigos()
        for tabla, para_que in NO_SE_PASAN.items():
            if tabla in self.origen.tablas():
                n = self.origen.contar(tabla)
                if n:
                    self.informe.no_pasadas[tabla] = (n, para_que)

    # ---------------------------------------------------------------- Ayudas

    def _leer(self, tabla):
        filas = self.origen.filas(tabla, COLUMNAS[tabla])
        self.informe.leidas[tabla] = len(filas)
        return filas

    def _hora(self, valor):
        """Fecha y hora sin zona (como las guardaba MySQL) → con la zona de Lima."""
        if valor is None or not isinstance(valor, datetime):
            return valor
        return valor if valor.tzinfo else timezone.make_aware(valor, self.zona)

    def _creado(self, valor):
        return self._hora(valor) or self.ahora

    def _valor(self, valor, validos, por_defecto, donde):
        if valor in validos:
            return valor
        self.informe.avisos.append(f"{donde}: el valor «{valor}» no existe en el sistema nuevo; se usó «{por_defecto}».")
        return por_defecto

    def _tabla(self, tabla, modelo, construir, padres=(), rutas=()):
        """Pasa una tabla. `padres`: [(columna, tabla_padre)]; la fila se omite si su padre no se pasó.
        `construir(fila)` devuelve los campos del modelo nuevo. `rutas`: campos que guardan archivos subidos."""
        objetos = []
        for fila in self._leer(tabla):
            falta = next((p for col, p in padres if fila[col] not in self.ids[p]), None)
            if falta is not None:
                self.informe.omitir(tabla, f"depende de {falta} que no se pasó")
                continue
            campos = construir(fila)
            if campos is None:
                continue
            for nombre, valor in list(campos.items()):
                if isinstance(valor, str):
                    campo = modelo._meta.get_field(nombre)
                    largo = getattr(campo, "max_length", None)
                    if largo and len(valor) > largo:
                        campos[nombre] = valor[:largo]
                        self.informe.avisos.append(
                            f"{tabla} #{fila.get('id', '')}: «{nombre}» era muy largo y se cortó a {largo}."
                        )
            for nombre in rutas:
                if campos.get(nombre):
                    self.rutas.add(campos[nombre])
            objetos.append(modelo(**campos))
        with _sin_fechas_automaticas(modelo):
            modelo.objects.bulk_create(objetos, batch_size=500)
        self.ids[tabla] = {o.pk for o in objetos}
        self.informe.importadas[tabla] = len(objetos)
        self.modelos.append(modelo)

    # ---------------------------------------------------------------- Personas

    def _importar_usuarios(self):
        def construir(f):
            es_prueba = bool(f["es_prueba"])
            if es_prueba and not self.con_cuentas_de_prueba:
                self.informe.omitir("usuarios", "cuenta del antiguo modo prueba")
                return None
            rol = self._valor(f["rol"], Rol.values, Rol.ALUMNO, f"usuarios #{f['id']} rol")
            perfil = self._perfiles.get(f["id"], {})
            origen = self._valor(
                perfil.get("origen") or Origen.ADMIN, Origen.values, Origen.ADMIN, f"av_perfiles #{f['id']} origen"
            )
            es_admin = rol == Rol.ADMIN
            try:
                password, desconocida = clave_django(f["password_hash"]), False
            except ClaveDesconocida as e:
                password, desconocida = make_password(None), True
                self.claves_desconocidas.append((f["id"], rol, e.formato))
            return dict(
                id=f["id"],
                dni=(f["dni"] or "").strip() or None,
                nombres=f["nombres"] or "",
                apellidos=f["apellidos"] or "",
                correo=(f["correo"] or "").strip().lower() or None,
                telefono=f["telefono"] or "",
                fecha_nacimiento=perfil.get("fecha_nacimiento"),
                rol=rol,
                origen=origen,
                debe_cambiar_clave=bool(perfil.get("cambiar_clave")) or desconocida,
                activado=self._hora(perfil.get("activado_at")),
                is_active=bool(f["activo"]) and not es_prueba and not desconocida,
                is_staff=es_admin,
                is_superuser=es_admin,
                password=password,
                creado=self._creado(f["created_at"]),
            )

        self._tabla("usuarios", Usuario, construir)
        self._revisar_claves_desconocidas()
        self.ids["av_perfiles"] = set(self._perfiles) & self.ids["usuarios"]
        self.informe.importadas["av_perfiles"] = len(self.ids["av_perfiles"])  # se juntaron con la persona
        self.informe.leidas["av_perfiles"] = len(self._perfiles)

    def _revisar_claves_desconocidas(self):
        """Sin contraseña conocida una cuenta activa podría ser reclamada con solo el DNI: o se frena, o pasa desactivada."""
        if not self.claves_desconocidas:
            return
        lista = ", ".join(f"#{i} ({rol}, {formato})" for i, rol, formato in self.claves_desconocidas[:20])
        if len(self.claves_desconocidas) > 20:
            lista += f" … y {len(self.claves_desconocidas) - 20} más"
        if not self.desactivar_claves_desconocidas:
            raise MigracionError(
                f"Hay {len(self.claves_desconocidas)} cuenta(s) con una contraseña en un formato que no reconozco (no es bcrypt): "
                f"{lista}. Si se pasaran así, quedarían como «alumno sin contraseña» y cualquiera que sepa su DNI podría "
                "reclamarlas. No se guardó nada. Opciones: restablece esas contraseñas en la base anterior y repite, o corre con "
                "--desactivar-claves-desconocidas para pasarlas desactivadas (después las reactivas con una contraseña nueva)."
            )
        self.informe.avisos.append(
            f"{len(self.claves_desconocidas)} cuenta(s) tenían una contraseña en un formato desconocido y pasaron DESACTIVADAS: "
            f"{lista}. Pon una contraseña nueva a cada una y actívala."
        )

    def _importar_preferencias(self):
        self._tabla(
            "av_preferencias",
            Preferencia,
            lambda f: dict(
                usuario_id=f["usuario_id"],
                tamano_letra=self._valor(
                    f["tamano_letra"], TamanoLetra.values, TamanoLetra.NORMAL, "av_preferencias.tamano_letra"
                ),
                alto_contraste=bool(f["alto_contraste"]),
                lectura_voz=bool(f["lectura_voz"]),
                modo_asistente=self._valor(f["modo_asistente"], ("escrito", "voz"), "escrito", "av_preferencias.modo_asistente"),
                actualizado=self._creado(f["updated_at"]),
            ),
            padres=[("usuario_id", "usuarios")],
        )

    # ---------------------------------------------------------------- Módulos

    def _importar_modulos(self):
        inscripciones = {f["curso_id"]: f for f in self._leer("av_inscripcion")}

        def construir(f):
            ins = inscripciones.get(f["id"], {})
            return dict(
                id=f["id"],
                nombre=f["nombre"],
                especialidad=f["especialidad"],
                modulo=f["modulo"] or "",
                periodo=f["periodo"],
                turno=self._valor(f["turno"], ("mañana", "tarde", "noche"), "mañana", f"cursos #{f['id']} turno"),
                horario=f["horario"] or "",
                docente_id=f["docente_id"],
                activo=bool(f["activo"]),
                creado=self._creado(f["created_at"]),
                codigo=(ins.get("codigo") or "").strip().upper() or None,
                inscripcion_abierta=bool(ins.get("abierta", True)),
                whatsapp_grupo=ins.get("whatsapp_grupo") or "",
            )

        self._tabla("cursos", Modulo, construir, padres=[("docente_id", "usuarios")])
        self.informe.importadas["av_inscripcion"] = len([i for i in inscripciones if i in self.ids["cursos"]])

        self._tabla(
            "matriculas",
            Matricula,
            lambda f: dict(id=f["id"], modulo_id=f["curso_id"], alumno_id=f["alumno_id"], creado=self._creado(f["created_at"])),
            padres=[("curso_id", "cursos"), ("alumno_id", "usuarios")],
        )
        self._tabla(
            "av_unidades_didacticas",
            UnidadDidactica,
            lambda f: dict(
                id=f["id"],
                modulo_id=f["curso_id"],
                nombre=f["nombre"],
                creditos=f["creditos"],
                horas=f["horas"],
                orden=f["orden"] or 0,
            ),
            padres=[("curso_id", "cursos")],
        )
        self._tabla(
            "av_evaluacion",
            Evaluacion,
            lambda f: dict(
                modulo_id=f["curso_id"],
                peso_tareas=f["peso_tareas"],
                peso_tests=f["peso_tests"],
                peso_asistencia=f["peso_asistencia"],
                nota_minima=f["nota_minima"],
            ),
            padres=[("curso_id", "cursos")],
        )

    # ---------------------------------------------------------------- Clases, materiales y tareas

    def _importar_clases_y_contenido(self):
        self._tabla(
            "av_unidades",
            Clase,
            lambda f: dict(
                id=f["id"],
                modulo_id=f["curso_id"],
                titulo=f["titulo"],
                descripcion=f["descripcion"] or "",
                orden=f["orden"] or 1,
                visible=bool(f["visible"]),
                fecha_inicio=f["fecha_inicio"],
                fecha_fin=f["fecha_fin"],
                estado=self._valor(f["estado"], ("auto", "abierta", "cerrada"), "auto", f"av_unidades #{f['id']} estado"),
                creado=self._creado(f["created_at"]),
            ),
            padres=[("curso_id", "cursos")],
        )
        self._tabla(
            "av_materiales",
            Material,
            lambda f: dict(
                id=f["id"],
                clase_id=f["unidad_id"],
                titulo=f["titulo"],
                descripcion=f["descripcion"] or "",
                tipo=self._valor(f["tipo"], TipoMaterial.values, TipoMaterial.ARCHIVO, f"av_materiales #{f['id']} tipo"),
                archivo_ruta=f["archivo_ruta"] or "",
                archivo_nombre=f["archivo_nombre"] or "",
                url=f["url"] or "",
                creado=self._creado(f["created_at"]),
                eliminado=self._hora(f["eliminado_at"]),
            ),
            padres=[("unidad_id", "av_unidades")],
            rutas=("archivo_ruta",),
        )
        self._tabla(
            "av_tareas",
            Tarea,
            lambda f: dict(
                id=f["id"],
                clase_id=f["unidad_id"],
                titulo=f["titulo"],
                instrucciones=f["instrucciones"] or "",
                criterios=f["criterios"] or "",
                archivo_ruta=f["archivo_ruta"] or "",
                archivo_nombre=f["archivo_nombre"] or "",
                fecha_limite=self._hora(f["fecha_limite"]),
                puntaje_max=f["puntaje_max"],
                politica_tardia=self._valor(
                    f["politica_tardia"], PoliticaTardia.values, PoliticaTardia.NO_ACEPTA, f"av_tareas #{f['id']} politica_tardia"
                ),
                penalidad_puntos=f["penalidad_puntos"],
                tipo_calificacion=self._valor(
                    f["tipo_calificacion"],
                    TipoCalificacion.values,
                    TipoCalificacion.NOTA,
                    f"av_tareas #{f['id']} tipo_calificacion",
                ),
                tipo=self._valor(f["tipo"], TipoTarea.values, TipoTarea.INDIVIDUAL, f"av_tareas #{f['id']} tipo"),
                creado=self._creado(f["created_at"]),
                eliminado=self._hora(f["eliminado_at"]),
            ),
            padres=[("unidad_id", "av_unidades")],
            rutas=("archivo_ruta",),
        )
        self._tabla(
            "av_entregas",
            Entrega,
            lambda f: dict(
                id=f["id"],
                tarea_id=f["tarea_id"],
                alumno_id=f["alumno_id"],
                archivo_ruta=f["archivo_ruta"] or "",
                archivo_nombre=f["archivo_nombre"] or "",
                enlace=f["enlace"] or "",
                comentario_alumno=f["comentario_alumno"] or "",
                fecha_entrega=self._creado(f["fecha_entrega"]),
                tardia=bool(f["tardia"]),
                nota=f["nota"],
                aprobado=None if f["aprobado"] is None else bool(f["aprobado"]),
                comentario_docente=f["comentario_docente"] or "",
                calificado=self._hora(f["calificado_at"]),
                retro_ruta=f["retro_ruta"] or "",
                retro_nombre=f["retro_nombre"] or "",
                creado=self._creado(f["created_at"]),
            ),
            padres=[("tarea_id", "av_tareas"), ("alumno_id", "usuarios")],
            rutas=("archivo_ruta", "retro_ruta"),
        )

    # ---------------------------------------------------------------- Asistencia, avisos, preguntas y mensajes

    def _importar_asistencia_y_comunicacion(self):
        self._tabla(
            "av_sesiones",
            SesionAsistencia,
            lambda f: dict(
                id=f["id"], modulo_id=f["curso_id"], fecha=f["fecha"], tema=f["tema"] or "", creado=self._creado(f["created_at"])
            ),
            padres=[("curso_id", "cursos")],
        )
        self._tabla(
            "av_asistencias",
            Asistencia,
            lambda f: dict(
                id=f["id"],
                sesion_id=f["sesion_id"],
                alumno_id=f["alumno_id"],
                estado=self._valor(f["estado"], Estado.values, Estado.FALTA, f"av_asistencias #{f['id']} estado"),
                observacion=f["observacion"] or "",
                creado=self._creado(f["created_at"]),
            ),
            padres=[("sesion_id", "av_sesiones"), ("alumno_id", "usuarios")],
        )
        self._tabla(
            "av_anuncios",
            Aviso,
            lambda f: dict(
                id=f["id"],
                modulo_id=f["curso_id"],
                autor_id=f["autor_id"],
                titulo=f["titulo"],
                contenido=f["contenido"],
                creado=self._creado(f["created_at"]),
            ),
            padres=[("curso_id", "cursos"), ("autor_id", "usuarios")],
        )

        # Preguntas de la clase: una respuesta solo se pasa si se pasó la pregunta a la que responde.
        pasadas = set()

        def construir_pregunta_clase(f):
            if f["padre_id"] is not None and f["padre_id"] not in pasadas:
                self.informe.omitir("av_preguntas_clase", "responde a una pregunta que no se pasó")
                return None
            pasadas.add(f["id"])
            return dict(
                id=f["id"],
                clase_id=f["unidad_id"],
                autor_id=f["autor_id"],
                padre_id=f["padre_id"],
                texto=f["texto"],
                creado=self._creado(f["created_at"]),
            )

        self._tabla(
            "av_preguntas_clase",
            PreguntaClase,
            construir_pregunta_clase,
            padres=[("unidad_id", "av_unidades"), ("autor_id", "usuarios")],
        )
        self._tabla(
            "av_notificaciones",
            Notificacion,
            lambda f: dict(
                id=f["id"],
                usuario_id=f["usuario_id"],
                mensaje=f["mensaje"],
                enlace=f["enlace"] or "",
                leida=bool(f["leida"]),
                creado=self._creado(f["created_at"]),
            ),
            padres=[("usuario_id", "usuarios")],
        )
        self._tabla(
            "av_conversaciones",
            Conversacion,
            lambda f: dict(
                id=f["id"],
                modulo_id=f["curso_id"],
                docente_id=f["docente_id"],
                alumno_id=f["alumno_id"],
                actualizado=self._creado(f["updated_at"]),
                creado=self._creado(f["created_at"]),
            ),
            padres=[("curso_id", "cursos"), ("docente_id", "usuarios"), ("alumno_id", "usuarios")],
        )
        self._tabla(
            "av_mensajes",
            Mensaje,
            lambda f: dict(
                id=f["id"],
                conversacion_id=f["conversacion_id"],
                autor_id=f["autor_id"],
                texto=f["texto"] or "",
                leido=self._hora(f["leido_at"]),
                archivo_ruta=f["archivo_ruta"] or "",
                archivo_nombre=f["archivo_nombre"] or "",
                creado=self._creado(f["created_at"]),
            ),
            padres=[("conversacion_id", "av_conversaciones"), ("autor_id", "usuarios")],
            rutas=("archivo_ruta",),
        )

    # ---------------------------------------------------------------- Formularios

    def _importar_formularios(self):
        self._tabla(
            "av_cuestionarios",
            Formulario,
            lambda f: dict(
                id=f["id"],
                clase_id=f["unidad_id"],
                modo=self._valor(f["modo"], tuple(MODOS), "examen", f"av_cuestionarios #{f['id']} modo"),
                titulo=f["titulo"],
                instrucciones=f["instrucciones"] or "",
                mensaje_final=f["mensaje_final"] or "",
                fecha_inicio=self._hora(f["fecha_inicio"]),
                fecha_limite=self._hora(f["fecha_limite"]),
                tiempo_minutos=f["tiempo_minutos"],
                intentos_max=f["intentos_max"] or 1,
                mezclar=bool(f["mezclar"]),
                mostrar_respuestas=bool(f["mostrar_respuestas"]),
                publicado=bool(f["publicado"]),
                creado=self._creado(f["created_at"]),
                eliminado=self._hora(f["eliminado_at"]),
            ),
            padres=[("unidad_id", "av_unidades")],
        )
        self._tabla(
            "av_preguntas",
            Pregunta,
            lambda f: dict(
                id=f["id"],
                formulario_id=f["cuestionario_id"],
                tipo=self._valor(f["tipo"], tuple(TIPOS), "abierta", f"av_preguntas #{f['id']} tipo"),
                enunciado=f["enunciado"] or "",
                ayuda=f["ayuda"] or "",
                imagen_ruta=f["imagen_ruta"] or "",
                obligatoria=bool(f["obligatoria"]),
                puntos=f["puntos"],
                respuestas_aceptadas=f["respuestas_aceptadas"] or "",
                explicacion=f["explicacion"] or "",
                permite_otra=bool(f["permite_otra"]),
                escala_min=f["escala_min"],
                escala_max=f["escala_max"],
                etiqueta_min=f["etiqueta_min"] or "",
                etiqueta_max=f["etiqueta_max"] or "",
                orden=f["orden"] or 1,
            ),
            padres=[("cuestionario_id", "av_cuestionarios")],
            rutas=("imagen_ruta",),
        )
        self._tabla(
            "av_opciones",
            Opcion,
            lambda f: dict(
                id=f["id"],
                pregunta_id=f["pregunta_id"],
                grupo=self._valor(f["grupo"], ("opcion", "fila", "columna"), "opcion", f"av_opciones #{f['id']} grupo"),
                texto=f["texto"] or "",
                correcta=bool(f["correcta"]),
                orden=f["orden"] or 1,
            ),
            padres=[("pregunta_id", "av_preguntas")],
        )
        self._tabla(
            "av_intentos",
            Intento,
            lambda f: dict(
                id=f["id"],
                formulario_id=f["cuestionario_id"],
                alumno_id=f["alumno_id"],
                inicio=self._creado(f["inicio"]),
                fin=self._hora(f["fin"]),
                fuera_tiempo=bool(f["fuera_tiempo"]),
                puntaje=f["puntaje"],
                puntaje_max=f["puntaje_max"],
                nota=f["nota"],
                revisado=bool(f["revisado"]),
                comentario=f["comentario"] or "",
            ),
            padres=[("cuestionario_id", "av_cuestionarios"), ("alumno_id", "usuarios")],
        )
        self._tabla(
            "av_respuestas",
            Respuesta,
            lambda f: dict(
                id=f["id"],
                intento_id=f["intento_id"],
                pregunta_id=f["pregunta_id"],
                opciones=f["opciones"] or "",
                texto=f["texto"] or "",
                archivo_ruta=f["archivo_ruta"] or "",
                archivo_nombre=f["archivo_nombre"] or "",
                puntos=f["puntos"],
                comentario=f["comentario"] or "",
            ),
            padres=[("intento_id", "av_intentos"), ("pregunta_id", "av_preguntas")],
            rutas=("archivo_ruta",),
        )

    # ---------------------------------------------------------------- Registro de actividad y ajustes

    def _importar_registro_y_ajustes(self):
        self._tabla(
            "av_registro",
            Registro,
            lambda f: dict(
                id=f["id"],
                usuario_id=f["usuario_id"] if f["usuario_id"] in self.ids["usuarios"] else None,
                accion=f["accion"],
                detalle=f["detalle"] or "",
                ip=f["ip"] or "",
                creado=self._creado(f["created_at"]),
            ),
        )

        def construir_ajuste(f):
            if f["clave"] in AJUSTES_CON_ARCHIVO and f["valor"]:
                self.rutas.add(f["valor"])
            return dict(clave=f["clave"], valor=f["valor"] or "", actualizado=self._creado(f["updated_at"]))

        self._tabla("av_configuracion", Ajuste, construir_ajuste)

    def _completar_codigos(self):
        """Los módulos que no tenían código de inscripción reciben uno."""
        for modulo in Modulo.objects.filter(codigo__isnull=True):
            modulo.nuevo_codigo()

    def _reiniciar_contadores(self):
        """Los números siguientes (id) siguen después del último que se pasó, no desde 1."""
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), self.modelos):
                cursor.execute(sql)

    # ---------------------------------------------------------------- Archivos subidos

    def _archivos(self):
        if self.carpeta is None:
            return
        if not self.carpeta.is_dir():
            raise MigracionError(f"No encuentro la carpeta de archivos del sistema anterior: {self.carpeta}")
        self.informe.archivos_revisados = True
        destino = Path(settings.MEDIA_ROOT)
        for ruta in sorted(self.rutas):
            relativa = Path(ruta.replace("\\", "/"))
            if relativa.is_absolute() or ".." in relativa.parts:
                self.informe.avisos.append(f"Se ignoró la ruta de archivo «{ruta}» porque sale de la carpeta de archivos.")
                continue
            fuente = self.carpeta / relativa
            if not fuente.is_file() or self.carpeta not in fuente.resolve().parents:
                self.informe.archivos_faltan.append(ruta)
                continue
            final = destino / relativa
            if final.exists():
                self.informe.archivos_ya_estaban += 1
                continue
            if not self.solo_revisar:
                final.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fuente, final)
            self.informe.archivos_copiados += 1
