"""Módulos (con su docente, turno y alumnos), unidades didácticas y clases.

Palabras (igual que en pantalla):
  curso  = programa de estudios (la especialidad, ej. «Soporte Técnico»): su nombre está en `Modulo.especialidad`
  módulo = Módulo 1 o 2 de un curso → `Modulo` (antes la tabla `cursos`)
  unidad didáctica = lista informativa del módulo (nombre, créditos y horas) → `UnidadDidactica`
  clase  = lo que el docente abre con fechas de apertura y cierre → `Clase` (antes `av_unidades`)
"""

import random
import re
import unicodedata
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.nucleo.utils import MESES, fecha_larga

from . import resumen


class Turno(models.TextChoices):
    MANANA = "mañana", "Mañana"
    TARDE = "tarde", "Tarde"
    NOCHE = "noche", "Noche"


class ModuloQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(activo=True)

    def con_alumnos(self):
        return self.annotate(total_alumnos=models.Count("matriculas", distinct=True)).select_related("docente")

    def de_docente(self, docente):
        return self.filter(docente=docente, activo=True)

    def de_alumno(self, alumno):
        return self.filter(matriculas__alumno=alumno, activo=True)


class Modulo(models.Model):
    nombre = models.CharField(max_length=150)
    especialidad = models.CharField("curso", max_length=100)
    modulo = models.CharField(max_length=100, blank=True, default="")
    periodo = models.CharField(max_length=20)
    turno = models.CharField(max_length=10, choices=Turno.choices)
    horario = models.CharField(max_length=120, blank=True, default="")
    docente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="modulos_a_cargo")
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(default=timezone.now)
    # Inscripción: el código que el docente da a sus alumnos (ej. PEL4821, se muestra PEL-4821)
    codigo = models.CharField(max_length=7, unique=True, null=True, blank=True)
    inscripcion_abierta = models.BooleanField(default=True)
    whatsapp_grupo = models.CharField("grupo de WhatsApp", max_length=300, blank=True, default="")

    objects = ModuloQuerySet.as_manager()

    class Meta:
        verbose_name = "módulo"
        verbose_name_plural = "módulos"
        ordering = ["-activo", "especialidad", "nombre"]

    def __str__(self):
        return self.nombre

    @property
    def codigo_fmt(self):
        """PEL4821 → PEL-4821"""
        return f"{self.codigo[:3]}-{self.codigo[3:]}" if self.codigo else ""

    @classmethod
    def crear(cls, **datos):
        """Crea el módulo con su código de inscripción."""
        modulo = cls.objects.create(**datos)
        modulo.nuevo_codigo()
        return modulo

    def nuevo_codigo(self):
        """Le da (o le cambia) al módulo un código para inscribirse: 3 letras de la especialidad y 4 números."""
        sin_tildes = unicodedata.normalize("NFKD", self.especialidad).encode("ascii", "ignore").decode()
        letras = re.sub(r"[^A-Za-z]", "", sin_tildes).upper()[:3].ljust(3, "X")
        for _ in range(30):
            codigo = f"{letras}{random.randint(1000, 9999)}"
            if not Modulo.objects.filter(codigo=codigo).exists():
                self.codigo = codigo
                self.save(update_fields=["codigo"])
                return codigo
        raise RuntimeError("No se pudo generar un código libre.")

    @classmethod
    def por_codigo(cls, texto):
        """Busca un módulo activo por su código (acepta «pel-4821», «PEL 4821»…)."""
        codigo = re.sub(r"[^A-Za-z0-9]", "", texto or "").upper()
        if not re.fullmatch(r"[A-Z]{3}\d{4}", codigo):
            return None
        return cls.objects.filter(codigo=codigo, activo=True).select_related("docente").first()

    def es_docente(self, usuario):
        return usuario.is_authenticated and self.docente_id == usuario.pk

    def es_alumno(self, usuario):
        return usuario.is_authenticated and self.matriculas.filter(alumno=usuario).exists()

    def alumnos(self):
        """Alumnos activos del módulo, por apellido."""
        from apps.cuentas.models import Usuario

        return Usuario.objects.filter(matriculas__modulo=self, is_active=True).order_by("apellidos", "nombres")

    def matricular(self, alumno):
        """Inscribe al alumno. Devuelve True si no estaba inscrito."""
        _, creada = Matricula.objects.get_or_create(modulo=self, alumno=alumno)
        return creada

    def quitar_alumno(self, alumno):
        Matricula.objects.filter(modulo=self, alumno=alumno).delete()

    def resumen_al_eliminar(self):
        return resumen.resumen_al_eliminar(self)

    def tiene_registros_de_alumnos(self):
        return resumen.tiene_registros_de_alumnos(self)

    @transaction.atomic
    def eliminar_completo(self):
        """Elimina el módulo de verdad, con todo lo que tiene (clases, trabajos, notas, asistencia, mensajes,
        inscripciones…). Los archivos subidos se borran cuando la base ya quedó bien."""
        self.delete()

    @classmethod
    def periodos(cls):
        """Periodos que existen (el más nuevo primero)."""
        return list(cls.objects.exclude(periodo="").values_list("periodo", flat=True).distinct().order_by("-periodo"))

    @classmethod
    def contar_por_especialidad(cls):
        """Cuántos módulos tiene cada curso: {«Peluquería y Barbería»: 3, …}"""
        return dict(cls.objects.values_list("especialidad").annotate(n=models.Count("id")))

    @classmethod
    def conteos_admin(cls):
        return {
            "todos": cls.objects.count(),
            "activos": cls.objects.filter(activo=True).count(),
            "archivados": cls.objects.filter(activo=False).count(),
        }

    @classmethod
    def resumen_por_especialidad(cls):
        """Por curso: cuántos módulos activos, docentes y alumnos distintos tiene."""
        r = {}
        for e in (
            cls.objects.filter(activo=True)
            .values("especialidad")
            .annotate(modulos=models.Count("id"), docentes=models.Count("docente", distinct=True))
        ):
            r[e["especialidad"]] = {"modulos": e["modulos"], "docentes": e["docentes"], "alumnos": 0}
        for e in (
            Matricula.objects.filter(modulo__activo=True)
            .values("modulo__especialidad")
            .annotate(alumnos=models.Count("alumno", distinct=True))
        ):
            r.setdefault(e["modulo__especialidad"], {"modulos": 0, "docentes": 0, "alumnos": 0})["alumnos"] = e["alumnos"]
        return r


class Matricula(models.Model):
    """Un alumno inscrito en un módulo (puede estar en uno o en los dos módulos de un curso)."""

    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE, related_name="matriculas")
    alumno = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="matriculas")
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "matrícula"
        verbose_name_plural = "matrículas"
        constraints = [models.UniqueConstraint(fields=["modulo", "alumno"], name="matricula_unica")]

    def __str__(self):
        return f"{self.alumno} en {self.modulo}"


class UnidadDidactica(models.Model):
    """Unidad didáctica del plan de estudios: solo la lista del módulo (nombre, créditos y horas)."""

    MAX = 12  # cuántas puede tener un módulo

    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE, related_name="unidades_didacticas")
    nombre = models.CharField(max_length=150)
    creditos = models.PositiveSmallIntegerField(null=True, blank=True)
    horas = models.PositiveSmallIntegerField(null=True, blank=True)
    orden = models.SmallIntegerField(default=0)

    class Meta:
        verbose_name = "unidad didáctica"
        verbose_name_plural = "unidades didácticas"
        ordering = ["orden", "id"]

    def __str__(self):
        return self.nombre

    @classmethod
    @transaction.atomic
    def guardar_lista(cls, modulo, lista):
        """Reemplaza la lista del módulo por la nueva (el orden es el de la lista)."""
        cls.objects.filter(modulo=modulo).delete()
        cls.objects.bulk_create(
            [
                cls(modulo=modulo, nombre=u["nombre"], creditos=u["creditos"], horas=u["horas"], orden=i)
                for i, u in enumerate(lista)
            ]
        )

    @classmethod
    def copiar(cls, de_modulo, a_modulo):
        cls.guardar_lista(
            a_modulo,
            [{"nombre": u.nombre, "creditos": u.creditos, "horas": u.horas} for u in cls.objects.filter(modulo=de_modulo)],
        )

    @classmethod
    def de_formulario(cls, post):
        """Lee las filas del formulario: ud_nombre[], ud_creditos[] y ud_horas[]. Las filas sin nombre se ignoran.
        Devuelve (lista, error); si hay error, la lista viene vacía."""
        nombres = post.getlist("ud_nombre[]")
        creditos = post.getlist("ud_creditos[]")
        horas = post.getlist("ud_horas[]")
        lista = []
        for i, nombre in enumerate(nombres):
            nombre = re.sub(r"\s+", " ", nombre).strip()
            if not nombre:
                continue
            c = _numero(creditos[i] if i < len(creditos) else "", 40)
            h = _numero(horas[i] if i < len(horas) else "", 2000)
            if c is False or h is False:
                return [], f"Revisa «{nombre[:40]}»: los créditos van de 0 a 40 y las horas de 0 a 2000 (solo números)."
            lista.append({"nombre": nombre[:150], "creditos": c, "horas": h})
        if len(lista) > cls.MAX:
            return [], f"Un módulo puede tener hasta {cls.MAX} unidades didácticas."
        return lista, None

    @staticmethod
    def totales(unidades):
        """(créditos, horas) de toda la lista (solo cuenta lo que tiene número)."""
        return sum(u.creditos or 0 for u in unidades), sum(u.horas or 0 for u in unidades)


def _numero(valor, maximo):
    """Un entero entre 0 y `maximo`; None si está vacío; False si no es válido."""
    valor = (valor or "").strip()
    if valor == "":
        return None
    return int(valor) if valor.isdigit() and int(valor) <= maximo else False


class EstadoClase(models.TextChoices):
    AUTO = "auto", "Según las fechas"
    ABIERTA = "abierta", "Abierta"
    CERRADA = "cerrada", "Cerrada"


class Clase(models.Model):
    """Clase de un módulo (antes «semana»). Tiene fechas: se abre y se cierra sola, o el docente la abre
    o la cierra cuando quiere.

    Situación para el alumno:
      proxima: todavía no empieza (se ve el título y la fecha, no el contenido)
      abierta: se ve todo y se puede entregar
      cerrada: se ven los materiales, pero ya no se entregan tareas ni tests
    """

    SITUACIONES = {"proxima": "Próxima", "abierta": "Abierta", "cerrada": "Cerrada"}

    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE, related_name="clases")
    titulo = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, default="")
    orden = models.IntegerField(default=1)
    visible = models.BooleanField(default=True)
    fecha_inicio = models.DateField(null=True, blank=True)  # se abre sola este día (None = desde ya)
    fecha_fin = models.DateField(null=True, blank=True)  # se cierra sola después de este día (None = sin fin)
    estado = models.CharField(max_length=10, choices=EstadoClase.choices, default=EstadoClase.AUTO)
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "clase"
        verbose_name_plural = "clases"
        ordering = ["orden", "id"]

    def __str__(self):
        return self.titulo

    @property
    def situacion(self):
        return situacion_de(self.estado, self.fecha_inicio, self.fecha_fin)

    @property
    def situacion_texto(self):
        return self.SITUACIONES[self.situacion]

    @property
    def fechas_texto(self):
        """«Del 7 al 20 de octubre», «Desde el 7 de octubre»…"""
        ini, fin = self.fecha_inicio, self.fecha_fin
        if ini and fin:
            mes_a, mes_b = MESES[ini.month], MESES[fin.month]
            return f"Del {ini.day}{' de ' + mes_a if mes_a != mes_b else ''} al {fin.day} de {mes_b}"
        if ini:
            return f"Desde el {fecha_larga(ini)}"
        if fin:
            return f"Hasta el {fecha_larga(fin)}"
        return "Sin fechas"

    @classmethod
    def crear(cls, modulo, titulo, inicio=None, fin=None, descripcion=""):
        orden = (cls.objects.filter(modulo=modulo).aggregate(m=models.Max("orden"))["m"] or 0) + 1
        return cls.objects.create(
            modulo=modulo, titulo=titulo, descripcion=descripcion or "", orden=orden, fecha_inicio=inicio, fecha_fin=fin
        )

    def mover(self, antes):
        """Sube o baja la clase un lugar (cambia su orden con la de al lado)."""
        vecinas = Clase.objects.filter(modulo=self.modulo)
        if antes:
            vecina = vecinas.filter(orden__lt=self.orden).order_by("-orden").first()
        else:
            vecina = vecinas.filter(orden__gt=self.orden).order_by("orden").first()
        if vecina:
            self.orden, vecina.orden = vecina.orden, self.orden
            self.save(update_fields=["orden"])
            vecina.save(update_fields=["orden"])

    @staticmethod
    def temas_de_texto(texto):
        """Convierte el texto «un tema por línea» en una lista (quita viñetas y números del inicio)."""
        temas = []
        for linea in (texto or "").splitlines():
            linea = re.sub(r"^\s*(?:[-*•·]|\d+[.)-]|clase\s*\d+\s*[:.-])\s*", "", linea.strip(), flags=re.I).strip()
            if linea:
                temas.append(linea[:150])
        return temas[:40]

    @classmethod
    def planificar(cls, modulo, temas, desde, dias):
        """Crea varias clases seguidas, una por tema: la primera empieza en `desde` y cada una dura `dias` días.
        Sin `desde`, se crean sin fechas (abiertas hasta que el docente las cierre). Devuelve cuántas creó."""
        inicio = desde
        for tema in temas:
            if inicio is None:
                cls.crear(modulo, tema)
                continue
            fin = inicio + timedelta(days=dias - 1)
            cls.crear(modulo, tema, inicio, fin)
            inicio = fin + timedelta(days=1)
        return len(temas)

    def esta_vacia(self):
        """¿No tiene materiales, tareas ni formularios?"""
        return not any(funcion(self) for funcion in CONTENIDO_DE_CLASE)

    @staticmethod
    def terminadas(clases):
        """Un módulo terminó cuando tiene clases y todas están cerradas."""
        return bool(clases) and all(c.situacion == "cerrada" for c in clases)

    @staticmethod
    def actual(clases):
        """La clase que toca ahora: la abierta más reciente; si no hay, la próxima."""
        abiertas = [c for c in clases if c.situacion == "abierta"]
        if abiertas:
            return abiertas[-1]
        for c in clases:
            if c.situacion == "proxima":
                return c
        return clases[-1] if clases else None


# funciones(clase) → True si tiene contenido (las llenan materiales, tareas y formularios)
CONTENIDO_DE_CLASE = []


class Aviso(models.Model):
    """Aviso del docente para todo el módulo."""

    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE, related_name="avisos")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="avisos_publicados")
    titulo = models.CharField(max_length=150)
    contenido = models.TextField()
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "aviso"
        verbose_name_plural = "avisos"
        ordering = ["-creado", "-id"]

    def __str__(self):
        return self.titulo

    @classmethod
    def crear(cls, modulo, autor, contenido):
        titulo = contenido if len(contenido) <= 60 else contenido[:59] + "…"
        return cls.objects.create(modulo=modulo, autor=autor, titulo=titulo, contenido=contenido)

    @classmethod
    def de_alumno(cls, alumno, limite=5):
        """Avisos recientes (último mes) de todos los módulos activos del alumno."""
        desde = timezone.now() - timedelta(days=30)
        return list(
            cls.objects.filter(modulo__matriculas__alumno=alumno, modulo__activo=True, creado__gte=desde)
            .select_related("autor", "modulo")
            .order_by("-creado")[:limite]
        )


class PreguntaClase(models.Model):
    """Pregunta de la clase: un alumno pregunta y el docente (o sus compañeros) responden."""

    clase = models.ForeignKey(Clase, on_delete=models.CASCADE, related_name="preguntas")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preguntas_de_clase")
    padre = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="respuestas")
    texto = models.TextField()
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "pregunta de clase"
        verbose_name_plural = "preguntas de clase"
        ordering = ["id"]
        indexes = [models.Index(fields=["clase", "padre"], name="pregclase_idx")]

    def __str__(self):
        return self.texto[:60]

    @classmethod
    def de_clase(cls, clase):
        """Preguntas de una clase (la más nueva primero), cada una con sus respuestas en `.lista_respuestas`."""
        filas = list(cls.objects.filter(clase=clase).select_related("autor"))
        preguntas = {p.pk: p for p in filas if p.padre_id is None}
        for p in preguntas.values():
            p.lista_respuestas = []
        for r in filas:
            if r.padre_id in preguntas:
                preguntas[r.padre_id].lista_respuestas.append(r)
        return list(reversed(list(preguntas.values())))

    @classmethod
    def sin_responder(cls, docente):
        """Preguntas sin ninguna respuesta del docente en sus módulos (para avisarle)."""
        respondidas = cls.objects.filter(padre_id=models.OuterRef("pk"), autor=docente)
        return (
            cls.objects.filter(clase__modulo__docente=docente, padre__isnull=True)
            .annotate(respondida=models.Exists(respondidas))
            .filter(respondida=False)
            .count()
        )


def situacion_de(estado, inicio, fin, hoy=None):
    """Situación de una clase («proxima», «abierta» o «cerrada») según su estado y sus fechas."""
    if estado in ("abierta", "cerrada"):
        return estado
    hoy = hoy or timezone.localdate()
    if isinstance(inicio, datetime):
        inicio = inicio.date()
    if isinstance(fin, datetime):
        fin = fin.date()
    if inicio is not None and inicio > hoy:
        return "proxima"
    if fin is not None and fin < hoy:
        return "cerrada"
    return "abierta"


# ---- Lo que se cuenta al eliminar un módulo ----
resumen.registrar_contador("alumno inscrito", "alumnos inscritos", lambda m: m.matriculas.count())
resumen.registrar_contador("clase", "clases", lambda m: m.clases.count())
