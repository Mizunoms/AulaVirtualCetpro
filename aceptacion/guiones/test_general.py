import http.cookiejar
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib

import os

BASE = os.environ.get("BASE", "http://127.0.0.1:8090")
fallos = []


def ok(cond, msg):
    print(("  OK  " if cond else "  FALLA ") + msg)
    if not cond:
        fallos.append(msg)


class Cliente:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.csrf = ""

    def req(self, metodo, ruta, datos=None, archivos=None, seguir=True):
        url = BASE + ruta
        cab = {}
        cuerpo = None
        if archivos is not None:
            b = uuid.uuid4().hex
            partes = []
            for k, v in (datos or {}).items():
                partes.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (b, k, v)).encode())
            for k, (nombre, contenido, tipo) in archivos.items():
                partes.append(
                    (
                        '--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: %s\r\n\r\n'
                        % (b, k, nombre, tipo)
                    ).encode()
                    + contenido
                    + b"\r\n"
                )
            partes.append(("--%s--\r\n" % b).encode())
            cuerpo = b"".join(partes)
            cab["Content-Type"] = "multipart/form-data; boundary=" + b
        elif datos is not None:
            cuerpo = urllib.parse.urlencode(datos, doseq=True).encode()
            cab["Content-Type"] = "application/x-www-form-urlencoded"
        r = urllib.request.Request(url, data=cuerpo, headers=cab, method=metodo)
        op = self.op
        if not seguir:

            class NoRedir(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *a, **k):
                    return None

            op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj), NoRedir)
        try:
            resp = op.open(r)
            codigo, html, hdr = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            codigo, html, hdr = e.code, e.read(), e.headers
        try:
            texto = html.decode("utf-8")
        except UnicodeDecodeError:
            texto = ""
        m = re.search(r'name="csrfmiddlewaretoken" value="([A-Za-z0-9]+)"', texto)
        if m:
            self.csrf = m.group(1)
        for mal in ("Fatal error", "Warning:", "Notice:", "Deprecated:", "Uncaught", "Parse error"):
            if mal in texto:
                fallos.append('%s %s contiene "%s"' % (metodo, ruta, mal))
                i = texto.index(mal)
                print("  !!! " + re.sub(r"<[^>]+>", "", texto[i : i + 400]))
        return codigo, texto, hdr, html

    def get(self, ruta, **k):
        return self.req("GET", ruta, **k)

    def post(self, ruta, datos=None, archivos=None, **k):
        d = dict(datos or {})
        d.setdefault("csrfmiddlewaretoken", self.csrf)
        return self.req("POST", ruta, d, archivos, **k)

    def login(self, dni, clave):
        self.get("/login")
        return self.post("/login", {"usuario": dni, "clave": clave})


def png():
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 4 for _ in range(4))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"

print("== Sin sesión")
anon = Cliente()
c, t, h, _ = anon.get("/", seguir=False)
ok(c == 302 and "/login" in h.get("Location", ""), "sin sesión redirige a /login")
c, t, *_ = anon.get("/login")
ok(c == 200 and ("Entrar al aula" in t or "Entrar con tu cuenta" in t), "pantalla de login")
c, t, *_ = anon.post("/login", {"usuario": "20000001", "clave": "mala"})
ok("no son correctos" in t, "contraseña incorrecta muestra mensaje")
c, t, *_ = anon.req("POST", "/login", {"usuario": "20000001", "clave": "20000001", "csrfmiddlewaretoken": "x"})
ok(c == 403 and "recarga" in t, "POST sin token CSRF válido es rechazado (403)")
c, t, *_ = anon.get("/no-existe")
ok(c == 404, "ruta inexistente da 404")

print("== Docente")
doc = Cliente()
c, t, *_ = doc.login("20000001", "20000001")
ok("Hola, profe Rosa" in t, "docente entra y ve su Inicio")
ok(
    "Registrar asistencia de hoy" in t and "Asistencia del día: Pendiente" in t,
    "Inicio docente muestra la asistencia del día con su botón",
)
c, t, *_ = doc.get("/cursos")
ok("Peluquería y Barbería" in t and "Soporte Técnico" not in t, "Mis cursos: solo su curso")
c, t, *_ = doc.get("/cursos/1")
ok('id="clases"' in t and "Avisos generales" in t and "Agregar clases" in t and "Acciones del día" in t, "página del curso")
c, t, *_ = doc.get("/cursos/2", seguir=False)
ok(c == 403, "docente no puede ver curso ajeno (403)")
c, t, *_ = doc.get("/cursos/1/clases")
ok("Corte básico" in t, "clases y materiales")
c, t, *_ = doc.post("/cursos/1/clases", {"tema": "Corte degrafilado"})
ok("Clase agregada" in t and "Corte degrafilado" in t, "agrega clase 3")
sem3 = re.search(r'name="unidad_id" value="(\d+)"', t).group(1) if re.search(r'name="unidad_id" value="(\d+)"', t) else "3"
c, t, *_ = doc.post(
    "/cursos/1/materiales",
    {"unidad_id": sem3, "tipo": "archivo", "titulo": "Guía de degrafilado"},
    {"archivo": ("guia.pdf", PDF, "application/pdf")},
)
ok("Material publicado" in t, "sube un PDF")
c, t, *_ = doc.post(
    "/cursos/1/materiales",
    {"unidad_id": sem3, "tipo": "archivo", "titulo": "Malo"},
    {"archivo": ("virus.php", b"<?php echo 1;", "application/pdf")},
)
ok("no está permitido" in t, "rechaza archivo .php")
c, t, *_ = doc.post(
    "/cursos/1/materiales",
    {"unidad_id": sem3, "tipo": "archivo", "titulo": "Falso"},
    {"archivo": ("falso.pdf", b"hola esto no es pdf", "application/pdf")},
)
ok("no parece ser" in t, "rechaza archivo con MIME falso")
c, t, *_ = doc.post(
    "/cursos/1/materiales", {"unidad_id": sem3, "tipo": "enlace", "url": "https://www.youtube.com/watch?v=abc", "titulo": ""}
)
ok("Material publicado" in t and "Video" in t, "agrega enlace de YouTube como video")
mid = re.search(r'/materiales/(\d+)"', t).group(1)
c, t, h, raw = doc.get("/materiales/" + mid)
ok(c == 200 and raw.startswith(b"%PDF"), "descarga el PDF por el controlador")
c, t, *_ = doc.post("/cursos/1/avisos", {"contenido": "El viernes no hay clase por feriado."})
ok("Aviso publicado" in t, "publica aviso")
c, t, *_ = doc.get("/cursos/1/tareas/nueva")
ok(
    "Nombre de la tarea" in t and 'name="criterio_texto[]"' in t and 'name="criterio_puntos[]"' in t,
    "formulario nueva tarea (con criterios de evaluación y puntos)",
)
c, t, *_ = doc.post(
    "/cursos/1/tareas",
    {
        "titulo": "Práctica: peinado",
        "instrucciones": "Sube una foto.",
        "criterios": "Peinado parejo\nOrden y limpieza",
        "fecha": "2030-01-01",
        "hora": "23:59",
        "politica_tardia": "no_acepta",
        "tipo_calificacion": "nota",
        "tipo": "individual",
        "unidad_id": sem3,
    },
)
ok("Tarea publicada" in t and "Compartir en WhatsApp" in t, "publica tarea y ofrece WhatsApp")
c, t, *_ = doc.post("/cursos/1/tareas", {"titulo": "", "fecha": "2030-01-01", "hora": "23:59"})
ok("Escribe el nombre" in t, "valida nombre vacío")
c, t, *_ = doc.get("/cursos/1/asistencia")
ok("Asistencia de hoy" in t and "Vino" in t, "pantalla de asistencia")
ids = sorted(set(re.findall(r'name="estado\[(\d+)\]"', t)))
datos = {"fecha": re.search(r'name="fecha" value="([\d-]+)"', t).group(1), "tema": "Práctica"}
for i in ids:
    datos["estado[%s]" % i] = "presente"
datos["estado[%s]" % ids[-1]] = "falta"
c, t, *_ = doc.post("/cursos/1/asistencia", datos)
ok("Asistencia guardada. Faltaron 1." in t, "guarda asistencia con 1 falta")
c, t, *_ = doc.post("/cursos/1/asistencia", {"fecha": "2099-01-01"})
ok("fecha válida" in t, "no deja guardar asistencia en el futuro")

print("== Alumno")
al = Cliente()
c, t, *_ = al.login("30000001", "30000001")
ok("Hola, Ana" in t, "alumno entra")
ok("Ya pasó la fecha" in t and "Próximas" in t and "Subir foto o archivo" in t, "Inicio agrupa tareas por fecha")
ok("El viernes no hay clase" in t, "ve el aviso del docente")
c, t, *_ = al.get("/cursos")
ok("Peluquería" in t and "Panadería" in t, "ve sus 2 cursos")
c, t, *_ = al.get("/cursos/2", seguir=False)
ok(c == 403, "alumno no ve curso donde no está matriculado")
c, t, *_ = al.get("/cursos/1/tareas/nueva", seguir=False)
ok(c == 403, "alumno no puede crear tareas")
c, t, *_ = al.get("/por-calificar", seguir=False)
ok(c == 403, "alumno no entra a Por calificar")
c, t, *_ = al.get("/tareas/2")
ok(
    "Tomar foto" in t and "Confirmar y enviar tarea" in t and "data-requiere-archivo" in t,
    "ficha de entrega: foto y botón que se activa al elegir archivo",
)
c, t, *_ = al.post("/tareas/2/entregar", {"comentario": "Listo profe"}, {"foto": ("foto.png", png(), "image/png")})
ok("Tarea entregada" in t, "entrega foto a tiempo")
c, t, *_ = al.post("/tareas/1/entregar", {}, {"archivo": ("hoja.pdf", PDF, "application/pdf")})
ok("Tarea entregada" in t and "Entrega tarde" in t, "entrega tarde (con penalidad)")
c, t, *_ = al.post("/tareas/3/entregar", {}, {})
ok("Toma una foto o elige" in t, "no deja enviar vacío")
c, t, *_ = al.get("/")
ok("Práctica: peinado" in t, "Inicio muestra la tarea nueva")
ent = re.search(r"/entregas/(\d+)/archivo", al.get("/tareas/2")[1]).group(1)
c, t, h, raw = al.get("/entregas/%s/archivo" % ent)
ok(c == 200 and raw.startswith(b"\x89PNG"), "alumno ve su foto entregada")
al2 = Cliente()
al2.login("30000003", "30000003")
c, t, *_ = al2.get("/entregas/%s/archivo" % ent, seguir=False)
ok(c == 403, "otro alumno NO puede ver esa foto")
c, t, *_ = al2.get("/cursos/3", seguir=False)
ok(c == 403, "alumno 3 no ve Panadería")

print("== Docente califica")
c, t, *_ = doc.get("/")
ok("2 trabajos por calificar" in t, "Inicio: 2 por calificar")
c, t, *_ = doc.get("/por-calificar")
ok("Ana María Quispe Rojas" in t and "Abrir y calificar evidencia" in t, "lista Por calificar")
eids = re.findall(r'href="[^"]*/entregas/(\d+)"', t)
c, t, *_ = doc.get("/entregas/" + eids[0])
ok("Nota del trabajo" in t, "pantalla calificar")
c, t, *_ = doc.post("/entregas/" + eids[0], {"nota": "25", "comentario": "", "siguiente": "0", "desde": "lista"})
ok("de 0 a 20" in t, "valida nota fuera de rango")
c, t, *_ = doc.post("/entregas/" + eids[0], {"nota": "17", "comentario": "Muy bien", "siguiente": "1", "desde": "lista"})
ok("guardada" in t, "guarda nota y pasa al siguiente")
pendientes = re.findall(r'href="[^"]*/entregas/(\d+)"', doc.get("/por-calificar")[1])
for e in pendientes:
    c, t, *_ = doc.post("/entregas/" + e, {"nota": "15", "comentario": "Entregó tarde", "siguiente": "0", "desde": "lista"})
c, t, *_ = doc.get("/por-calificar")
ok("Todo calificado" in t, "Por calificar queda vacío")
c, t, *_ = doc.get("/cursos/1/notas")
ok("Quispe Rojas" in t and "Descargar para Excel" in t, "libro de notas")
c, t, h, raw = doc.get("/cursos/1/notas/excel")
ok(c == 200 and raw.startswith(b"\xef\xbb\xbf") and "Nota final" in raw.decode("utf-8"), "descarga CSV para Excel")
print("     " + raw.decode("utf-8").splitlines()[3][:160])
print("     " + raw.decode("utf-8").splitlines()[4][:160])
c, t, *_ = doc.get("/cursos/1/notas/imprimir")
ok("Registro de notas" in t, "versión para imprimir")
c, t, *_ = doc.get("/tareas/2")
ok("Nota 17" in t or "Nota 15" in t, "lista de la tarea muestra notas")

print("== Alumno ve notas")
c, t, *_ = al.get("/notas")
ok("Nota final" in t and ("17" in t), "Mis notas muestra la nota")
ok("13" in t, "nota tardía con −2 puntos (15 → 13)")
ok(
    "tabla-boletin" in t and "Por entregar" in t and "de 1 clases" in t,
    "boletín: tabla de actividades y asistencia en el resumen",
)
ok(
    "badge-grade neutro" in t and "Tu trabajo calificado recientemente aparecerá aquí" in t and "Sin nota todavía" in t,
    "Mis notas: un módulo sin notas muestra «--» y el texto de ayuda",
)
ok("badge-grade aprueba" in t, "Mis notas: la nota final aprobada va en verde")
pein = re.search(r'/tareas/(\d+)">Práctica: peinado<', t)
ok(pein is not None, "boletín: la tarea pendiente aparece con su enlace")
c, t, *_ = al.get("/tareas/" + pein.group(1))
ok(
    "Cómo te van a calificar" in t and "Peinado parejo" in t and "Orden y limpieza" in t,
    "ficha: el alumno ve los criterios de la tarea",
)
c, t, *_ = al.get("/cursos/1/asistencia")
ok("Viniste a 1 de 1" in t, "Mi asistencia")
c, t, *_ = al.post("/cuenta/preferencias", {"tamano_letra": "grande", "alto_contraste": "1", "lectura_voz": "1"})
ok("guardamos tus cambios" in t and "letra-grande" in t and "alto-contraste" in t, "guarda letra grande y alto contraste")
c, t, *_ = al.post("/cuenta/clave", {"actual": "mala", "nueva": "nueva123", "repetir": "nueva123"})
ok("actual no es correcta" in t, "cambiar clave valida la actual")
c, t, *_ = al.post("/cuenta/clave", {"actual": "30000001", "nueva": "nueva123", "repetir": "nueva123"})
ok("se cambió" in t, "cambia contraseña")
c, t, *_ = Cliente().login("30000001", "nueva123")
ok("Hola, Ana" in t, "entra con la contraseña nueva")

print("== Administración")
adm = Cliente()
c, t, *_ = adm.login("10000001", "CetproAdmin2026")
ok("Docentes" in t and "Módulos activos" in t, "admin entra")
c, t, *_ = adm.get("/admin/usuarios")
ok("Paredes Huamán" in t, "lista usuarios")
c, t, *_ = adm.post(
    "/admin/usuarios",
    {
        "rol": "docente",
        "dni": "40000001",
        "nombres": "Profesora",
        "apellidos": "De Prueba",
        "telefono": "",
        "correo": "",
        "clave": "",
    },
)
ok("Cuenta creada" in t, "crea docente (contraseña generada)")
clave_prof = re.findall(r'<div class="valor"[^>]*>([^<]+)</div>', t)[-1]
c, t, *_ = adm.post(
    "/admin/usuarios",
    {"rol": "docente", "dni": "40000001", "nombres": "X", "apellidos": "Y", "telefono": "", "correo": "", "clave": ""},
)
ok("Ya existe" in t, "no permite DNI repetido")
c, t, *_ = adm.get("/admin/modulos/nuevo")
did = re.search(r'<option value="(\d+)"[^>]*>De Prueba, Profesora', t).group(1)
c, t, *_ = adm.post(
    "/admin/modulos",
    {
        "especialidad": "Peluquería y Barbería",
        "nombre": "Peluquería – Prueba",
        "modulo": "Módulo I",
        "periodo": "2026-II",
        "turno": "tarde",
        "horario": "",
        "docente_id": did,
    },
)
ok("Módulo creado" in t, "crea módulo")
cid = re.search(r"/admin/modulos/(\d+)/alumnos", t).group(1)
c, t, *_ = adm.post("/admin/modulos/%s/alumnos" % cid, {"lista": "30000002\n41111111, María Elena, Torres Soto\n123"})
ok(
    "2 alumnos agregados" in t and "creará" in t and "DNI de 8 números" in t,
    "inscribe por lista (nuevo queda pendiente y avisa error)",
)
ma = Cliente()
ma.get("/registro")
ma.post("/registro", {"dni": "41111111"})
c, t, *_ = ma.post("/registro/confirmar", {"telefono": ""})
ok("Tu cuenta está lista" in t, "alumna de la lista crea su contraseña con su DNI")
c, t, *_ = Cliente().login("rosa.paredes@cetpro.test", "20000001")
ok("Hola, profe Rosa" in t, "docente entra con su correo")
nuevo_prof = Cliente()
c, t, *_ = nuevo_prof.login("40000001", clave_prof)
ok(
    re.match(r"^[a-z2-9]{10}$", clave_prof) and clave_prof != "40000001" and "La contraseña que te dieron es temporal" in t,
    "sin contraseña escrita se crea una al azar (nunca el DNI) y la persona debe elegir la suya",
)
c, t, *_ = Cliente().login("40000001", "40000001")
ok("La contraseña que te dieron es temporal" not in t and "Hola, profe" not in t, "con el DNI como contraseña no se puede entrar")
c, t, *_ = nuevo_prof.get("/cursos", seguir=False)
ok(c in (301, 302, 303), "mientras no la cambie, el aula la manda a elegir su contraseña")
c, t, *_ = nuevo_prof.post("/cuenta/nueva-clave", {"nueva": clave_prof, "repetir": clave_prof})
ok("distinta de la que te dieron" in t, "no acepta repetir la contraseña temporal como contraseña nueva")
c, t, *_ = nuevo_prof.post("/cuenta/nueva-clave", {"nueva": "40000001", "repetir": "40000001"})
ok("distinta de la que te dieron" in t, "no acepta el DNI como contraseña nueva")
c, t, *_ = nuevo_prof.post("/cuenta/nueva-clave", {"nueva": "ClaveProfe2026", "repetir": "ClaveProfe2026"})
ok("Hola, profe Profesora" in t and "Peluquería – Prueba" in t, "docente nuevo elige su contraseña y ve su curso")
c, t, *_ = adm.get("/cursos/1")
ok("Notas y reportes" in t and "Nueva tarea" not in t, "admin ve curso en solo lectura")
c, t, *_ = doc.get("/admin/usuarios", seguir=False)
ok(c == 403, "docente no entra a administración")
dirc = Cliente()
c, t, *_ = dirc.login("10000002", "CetproAdmin2026")
c, t, h, raw = dirc.get("/cursos/1/notas/excel")
ok(c == 200 and raw.startswith(b"\xef\xbb\xbf"), "dirección descarga notas")
c, t, *_ = dirc.post("/cursos/1/avisos", {"contenido": "hack"}, seguir=False)
ok(c == 403, "dirección no puede publicar avisos")

import subprocess


def sql(q):
    """Consulta de solo lectura a la base de aceptación (PostgreSQL); devuelve filas de textos como lo hacía mysql.exe."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")) as con:
        filas = con.execute(q).fetchall()
    return [["" if v is None else str(v) for v in f] for f in filas]


def opciones_en(html):
    """texto de la alternativa -> (name, value) en la pantalla de responder."""
    r = {}
    for m in re.finditer(
        r'<input type="(?:radio|checkbox)" name="(op\[\d+\](?:\[\])?)" id="o(\d+)" value="\d+"[^>]*>\s*<label for="o\2">(.*?)</label>',
        html,
        re.S,
    ):
        texto = re.sub(r"<[^>]+>", " ", m.group(3))
        texto = re.sub(r"\s+", " ", texto).strip()
        texto = re.sub(r"^[A-Z] ", "", texto)
        r[texto] = (m.group(1), m.group(2))
    return r


print("== Examen de ejemplo (alumno)")
c, t, *_ = al.get("/")
ok("Examen" in t and "Dar el examen" in t, "Inicio del alumno muestra el examen pendiente")
c, t, *_ = al.get("/examenes/1?desde=inicio")
ok("Empezar el examen" in t and "15 minutos" in t, "portada del examen")
c, t, *_ = al.post("/examenes/1/empezar")
ok("Enviar</button>" in t and "Pregunta 1 de 5" in t and "data-segundos" in t, "empieza el examen con reloj")
intento1 = re.search(r'action="[^"]*/intentos/(\d+)"', t).group(1)
op = opciones_en(t)
pregs = {p: q for p, q in sql("SELECT tipo, id FROM av_preguntas WHERE cuestionario_id = 1")}
ok(len(op) == 10, "muestra las 10 alternativas")
resp = [
    (op["Peine de dientes anchos"][0], op["Peine de dientes anchos"][1]),
    (op["Verdadero"][0], op["Verdadero"][1]),
    (op["Guantes"][0], op["Guantes"][1]),
    (op["Mascarilla"][0], op["Mascarilla"][1]),
    (op["Capa para el cliente"][0], op["Capa para el cliente"][1]),
    ("txt[%s]" % pregs["corta"], "  DEGRADADO "),
    ("txt[%s]" % pregs["abierta"], "Lo saludo con amabilidad y le pregunto qué corte desea."),
    ("csrfmiddlewaretoken", al.csrf),
]
c, t, *_ = al.req("POST", "/intentos/" + intento1, resp)
ok("Enviado" in t and "la está revisando" in t and "8 de 10 puntos" in t, "corrige solo: 8 de 10 (la abierta queda por revisar)")
c, t, *_ = al.post("/intentos/" + intento1, {"csrfmiddlewaretoken": al.csrf})
ok("ya fue enviado" in t, "no deja enviar dos veces")
c, t, *_ = al2.get("/intentos/" + intento1, seguir=False)
ok(c == 403, "otro alumno no puede ver el examen de Ana")

print("== Docente revisa el examen")
c, t, *_ = doc.get("/por-calificar")
ok("Examen: Examen: corte básico" in t or "Examen: corte básico y bioseguridad" in t, "Por calificar muestra examen por revisar")
c, t, *_ = doc.get("/intentos/" + intento1)
ok("Puntos (0 a 2)" in t and "Lo saludo con amabilidad" in t, "docente ve la respuesta abierta")
c, t, *_ = doc.post("/intentos/" + intento1 + "/revisar", {"puntos[%s]" % pregs["abierta"]: "5", "siguiente": "0"})
ok("van de 0 a 2" in t, "no deja poner más puntos que los de la pregunta")
c, t, *_ = doc.post(
    "/intentos/" + intento1 + "/revisar",
    {"puntos[%s]" % pregs["abierta"]: "2", "comentario[%s]" % pregs["abierta"]: "Muy bien", "siguiente": "0"},
)
ok("Revisión guardada" in t and "Nota 20" in t, "revisión guardada: nota 20")
c, t, *_ = al.get("/examenes/1")
ok("Tu mejor nota" in t and "Responder otra vez" in t, "alumno ve su nota y puede dar otra vez (2 intentos)")
c, t, *_ = al.get("/notas")
ok("Examen: Examen: corte básico" in t or "Examen: corte básico" in t, "el examen aparece en Mis notas")
c, t, *_ = doc.post("/examenes/1/preguntas", {"tipo": "vf", "enunciado": "x", "puntos": "1", "vf_correcta": "v"})
ok("no se pueden cambiar las preguntas" in t, "no deja cambiar preguntas después de que alguien lo dio")

print("== Docente crea un examen nuevo")
c, t, *_ = doc.get("/cursos/1/examenes/nuevo")
ok("¿Qué vas a crear?" in t, "formulario de examen")
c, t, *_ = doc.post(
    "/cursos/1/examenes",
    {
        "titulo": "Práctica de colorimetría",
        "instrucciones": "",
        "fecha": "2030-01-01",
        "hora": "23:59",
        "tiempo_minutos": "0",
        "intentos_max": "1",
        "mostrar_respuestas": "1",
    },
)
ok("Formulario creado" in t and "Agregar pregunta 1" in t, "crea examen y abre el editor")
qid = re.search(r'action="[^"]*/examenes/(\d+)/preguntas"', t).group(1)
c, t, *_ = doc.post("/examenes/%s/publicar" % qid, {"publicar": "1"})
ok("al menos una pregunta" in t, "no deja publicar sin preguntas")
base = {
    "tipo": "opcion",
    "enunciado": "¿Qué color se obtiene al mezclar azul y amarillo?",
    "puntos": "4",
    "opcion[0]": "Verde",
    "opcion[1]": "Rojo",
    "opcion[2]": "Morado",
    "opcion[3]": "",
}
c, t, *_ = doc.post("/examenes/%s/preguntas" % qid, dict(base, **{"correctas[]": ["0", "1"]}))
ok("solo una" in t, "valida una sola correcta")
c, t, *_ = doc.post("/examenes/%s/preguntas" % qid, dict(base, **{"correctas[]": ["0"]}))
ok("Pregunta agregada" in t and "Agregar pregunta 2" in t, "agrega pregunta de alternativas")
c, t, *_ = doc.post(
    "/examenes/%s/preguntas" % qid,
    {
        "tipo": "multiple",
        "enunciado": "¿Cuáles son colores primarios?",
        "puntos": "4",
        "opcion[0]": "Rojo",
        "opcion[1]": "Azul",
        "opcion[2]": "Verde",
        "opcion[3]": "Amarillo",
        "correctas[]": ["0", "1", "3"],
    },
)
ok("Pregunta agregada" in t, "agrega pregunta de varias correctas")
c, t, *_ = doc.post(
    "/examenes/%s/preguntas" % qid, {"tipo": "vf", "enunciado": "El tinte se aplica sobre cabello mojado.", "puntos": "2"}
)
ok("Verdadero o Falso" in t, "valida verdadero/falso sin respuesta")
c, t, *_ = doc.post(
    "/examenes/%s/preguntas" % qid,
    {"tipo": "vf", "enunciado": "El tinte se aplica sobre cabello mojado.", "puntos": "2", "vf_correcta": "f"},
)
ok("Pregunta agregada" in t and "Agregar pregunta 4" in t, "agrega verdadero o falso")
p_ids = [x[0] for x in sql("SELECT id FROM av_preguntas WHERE cuestionario_id = %s ORDER BY orden" % qid)]
c, t, *_ = doc.post("/preguntas/%s/mover" % p_ids[2], {"dir": "arriba"})
nuevo_orden = [x[0] for x in sql("SELECT id FROM av_preguntas WHERE cuestionario_id = %s ORDER BY orden" % qid)]
ok(nuevo_orden == [p_ids[0], p_ids[2], p_ids[1]], "sube una pregunta")
c, t, *_ = doc.get("/preguntas/%s/editar" % p_ids[0])
ok("Guardar cambios" in t and "Verde" in t, "pantalla para cambiar pregunta")
c, t, *_ = doc.post("/preguntas/%s" % p_ids[0], dict(base, **{"correctas[]": ["0"], "puntos": "6"}))
ok("Pregunta guardada" in t, "cambia una pregunta")
c, t, *_ = doc.post("/examenes/%s/publicar" % qid, {"publicar": "1"})
ok("Publicado" in t and "12 puntos" in t, "publica el examen (12 puntos)")

print("== Otro alumno da el examen nuevo")
al5 = Cliente()
al5.login("30000005", "30000005")
c, t, *_ = al5.post("/examenes/%s/empezar" % qid)
ruta_intento = re.search(r'action="[^"]*(/intentos/\d+)"', t).group(1)


def opcion(pid, texto):
    oid = sql("SELECT id FROM av_opciones WHERE pregunta_id = %s AND texto = '%s'" % (pid, texto))[0][0]
    tipo = sql("SELECT tipo FROM av_preguntas WHERE id = %s" % pid)[0][0]
    return ("op[%s]%s" % (pid, "[]" if tipo == "multiple" else ""), oid)


c, t, *_ = al5.req(
    "POST",
    ruta_intento,
    [
        opcion(p_ids[0], "Verde"),
        opcion(p_ids[1], "Rojo"),
        opcion(p_ids[1], "Azul"),
        opcion(p_ids[2], "Falso"),
        ("csrfmiddlewaretoken", al5.csrf),
    ],
)
ok("8 de 12 puntos" in t and "13.33" in t, "nota calculada: 8/12 → 13.33 (varias correctas incompleta = 0)")
c, t, *_ = al5.post("/examenes/%s/empezar" % qid)
ok("todos tus intentos" in t, "no deja pasar del número de intentos")
c, t, *_ = doc.get("/examenes/%s/resultados?ver=personas" % qid)
ok("Nota 13.33" in t and "No respondió" in t, "resultados del docente")
c, t, *_ = doc.get("/examenes/%s" % qid)
ok("% la respondió bien" in t, "muestra % de aciertos por pregunta")
c, t, h, raw = doc.get("/cursos/1/notas/excel")
ok(
    "Examen: Práctica de colorimetría" in raw.decode("utf-8") and "13,33" in raw.decode("utf-8"),
    "el examen sale en la descarga para Excel",
)

print("== Formulario tipo Google Forms (trabajo)")
c, t, *_ = doc.get("/cursos/1/examenes/nuevo?modo=trabajo")
ok('id="modo-trabajo" value="trabajo" checked' in t, 'crear formulario con "Trabajo" elegido')
c, t, *_ = doc.post(
    "/cursos/1/examenes",
    {
        "modo": "trabajo",
        "titulo": "Ficha: mi primer corte",
        "instrucciones": "Cuéntanos cómo te fue.",
        "mensaje_final": "¡Gracias! Lo reviso esta semana.",
        "fecha": "2030-01-01",
        "hora": "23:59",
        "tiempo_minutos": "0",
        "intentos_max": "1",
        "mostrar_respuestas": "1",
    },
)
ok("Formulario creado" in t and "Trabajo" in t and "Puntos" not in t, "formulario de trabajo creado (sin puntos)")
fid = re.search(r'action="[^"]*/examenes/(\d+)/preguntas"', t).group(1)
P = "/examenes/%s/preguntas" % fid
c, t, *_ = doc.post(P, {"tipo": "seccion", "enunciado": "Parte 1: datos", "ayuda": "Responde sobre tu práctica"})
ok("Título agregado" in t, "agrega título de sección")
c, t, *_ = doc.post(
    P,
    {
        "tipo": "desplegable",
        "enunciado": "¿En qué turno estudias?",
        "opcion[0]": "Mañana",
        "opcion[1]": "Tarde",
        "opcion[2]": "Noche",
        "obligatoria": "1",
    },
)
ok("Pregunta agregada" in t, "agrega lista desplegable")
c, t, *_ = doc.post(
    P,
    {
        "tipo": "multiple",
        "enunciado": "¿Qué herramientas usaste?",
        "opcion[0]": "Tijera",
        "opcion[1]": "Navaja",
        "opcion[2]": "Peine",
        "permite_otra": "1",
        "obligatoria": "1",
    },
)
ok("Otra: …" in t, 'agrega casillas con opción "Otra"')
c, t, *_ = doc.post(
    P,
    {
        "tipo": "escala",
        "enunciado": "¿Qué tan fácil fue?",
        "escala_min": "1",
        "escala_max": "5",
        "etiqueta_min": "Difícil",
        "etiqueta_max": "Fácil",
        "obligatoria": "1",
    },
)
ok("1 (Difícil) → 5 (Fácil)" in t, "agrega escala lineal")
c, t, *_ = doc.post(P, {"tipo": "fecha", "enunciado": "¿Qué día hiciste el corte?", "obligatoria": "1"})
ok("Elige una fecha" in t, "agrega fecha")
c, t, *_ = doc.post(P, {"tipo": "hora", "enunciado": "¿A qué hora empezaste?"})
c, t, *_ = doc.post(
    P,
    {
        "tipo": "cuadricula",
        "enunciado": "Evalúa tu trabajo",
        "filas": "Limpieza\nAcabado",
        "columnas": "Bien\nRegular",
        "obligatoria": "1",
    },
)
ok("Filas:" in t and "Limpieza" in t, "agrega cuadrícula")
c, t, *_ = doc.post(P, {"tipo": "cuadricula", "enunciado": "Mala", "filas": "Una", "columnas": "Solo una"})
ok("2 columnas" in t, "valida columnas de cuadrícula")
c, t, *_ = doc.post(
    P,
    {"tipo": "archivo", "enunciado": "Sube la foto de tu corte", "obligatoria": "1"},
    {"imagen": ("modelo.png", png(), "image/png")},
)
ok("Pregunta agregada" in t and '/imagen"' in t, "agrega subir archivo con imagen en la pregunta")
img_pid = re.findall(r"/preguntas/(\d+)/imagen", t)[-1]
c, t, h, raw = doc.get("/preguntas/%s/imagen" % img_pid)
ok(c == 200 and raw.startswith(b"\x89PNG"), "la imagen de la pregunta se ve")
c, t, *_ = doc.post(P, {"tipo": "abierta", "enunciado": "¿Qué mejorarías?"})
pids = [x[0] for x in sql("SELECT id FROM av_preguntas WHERE cuestionario_id = %s ORDER BY orden" % fid)]
c, t, *_ = doc.post("/preguntas/%s/duplicar" % pids[-1])
ok(
    "Pregunta copiada" in t and len(sql("SELECT id FROM av_preguntas WHERE cuestionario_id = %s" % fid)) == len(pids) + 1,
    "duplica una pregunta",
)
dup = [x[0] for x in sql("SELECT id FROM av_preguntas WHERE cuestionario_id = %s ORDER BY orden" % fid)][-1]
doc.post("/preguntas/%s/eliminar" % dup)
c, t, *_ = doc.get("/examenes/%s/vista-previa" % fid)
ok("Vista previa" in t and "desactivado en la vista previa" in t and "Parte 1: datos" in t, "vista previa del formulario")
c, t, *_ = doc.post("/examenes/%s/publicar" % fid, {"publicar": "1"})
ok("Publicado" in t, "publica el formulario")

print("== Alumno responde el formulario")
c, t, *_ = al.get("/")
ok("Ficha: mi primer corte" in t and "Responder" in t, 'aparece en "Por hacer"')
c, t, *_ = al.post("/examenes/%s/empezar" % fid)
ruta_f = re.search(r'action="[^"]*(/intentos/\d+)"', t).group(1)
ok(
    'enctype="multipart/form-data"' in t and "Parte 1: datos" in t and "escala-numeros" in t and 'type="date"' in t,
    "muestra todos los tipos",
)
P_ = {r[1]: r[0] for r in sql("SELECT id, enunciado FROM av_preguntas WHERE cuestionario_id = %s" % fid)}
p_turno, p_herr, p_esc, p_fecha, p_hora, p_grid, p_arch, p_abierta = (
    P_[k]
    for k in [
        "¿En qué turno estudias?",
        "¿Qué herramientas usaste?",
        "¿Qué tan fácil fue?",
        "¿Qué día hiciste el corte?",
        "¿A qué hora empezaste?",
        "Evalúa tu trabajo",
        "Sube la foto de tu corte",
        "¿Qué mejorarías?",
    ]
)
oid = lambda pid, txt: sql("SELECT id FROM av_opciones WHERE pregunta_id = %s AND texto = '%s'" % (pid, txt))[0][0]
filas = [x[0] for x in sql("SELECT id FROM av_opciones WHERE pregunta_id = %s AND grupo = 'fila' ORDER BY orden" % p_grid)]
cols = [x[0] for x in sql("SELECT id FROM av_opciones WHERE pregunta_id = %s AND grupo = 'columna' ORDER BY orden" % p_grid)]
incompleto = [("op[%s]" % p_turno, oid(p_turno, "Tarde")), ("txt[%s]" % p_esc, "4"), ("csrfmiddlewaretoken", al.csrf)]
c, t, *_ = al.req("POST", ruta_f, incompleto)
ok(
    "Faltan responder las preguntas" in t and 'value="%s" selected' % oid(p_turno, "Tarde") in t,
    "obligatorias: avisa cuáles faltan y conserva lo respondido",
)
completo = [
    ("op[%s]" % p_turno, oid(p_turno, "Tarde")),
    ("op[%s][]" % p_herr, oid(p_herr, "Tijera")),
    ("op[%s][]" % p_herr, "otra"),
    ("otra[%s]" % p_herr, "Secadora"),
    ("txt[%s]" % p_esc, "4"),
    ("txt[%s]" % p_fecha, "2026-10-05"),
    ("txt[%s]" % p_hora, "09:30"),
    ("grid[%s][%s]" % (p_grid, filas[0]), cols[0]),
    ("grid[%s][%s]" % (p_grid, filas[1]), cols[1]),
    ("txt[%s]" % p_abierta, "Hacerlo más rápido."),
    ("csrfmiddlewaretoken", al.csrf),
]
c, t, *_ = (
    al.req("POST", ruta_f, completo + [("_x", "1")], seguir=True)
    if False
    else al.post(
        ruta_f, dict(completo, **{"csrfmiddlewaretoken": al.csrf}), {"archivo_%s" % p_arch: ("corte.png", png(), "image/png")}
    )
    if False
    else (None, None, None, None)
)
# multipart con campos repetidos (casillas): se arma a mano
b = uuid.uuid4().hex
partes = b""
for k, v in completo:
    partes += ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (b, k, v)).encode()
partes += (
    (
        '--%s\r\nContent-Disposition: form-data; name="archivo_%s"; filename="corte.png"\r\nContent-Type: image/png\r\n\r\n'
        % (b, p_arch)
    ).encode()
    + png()
    + b"\r\n"
)
partes += ("--%s--\r\n" % b).encode()
req = urllib.request.Request(
    BASE + ruta_f, data=partes, headers={"Content-Type": "multipart/form-data; boundary=" + b}, method="POST"
)
t = al.op.open(req).read().decode()
ok("¡Gracias! Lo reviso esta semana." in t, "envía el formulario y ve el mensaje final")
ok(
    "Otra: Secadora" in t
    and "Limpieza:" in t
    and "4 (de 1 a 5)" in t
    and "9:30 de la mañana" in t
    and "Tu profesor la está revisando" in t,
    "ve sus respuestas de cada tipo",
)
rid_arch = re.search(r"/respuestas/(\d+)/archivo", t).group(1)
c, t2, h, raw = al.get("/respuestas/%s/archivo" % rid_arch)
ok(c == 200 and raw.startswith(b"\x89PNG"), "el alumno ve su foto subida")
c, t2, *_ = al2.get("/respuestas/%s/archivo" % rid_arch, seguir=False)
ok(c == 403, "otro alumno no puede ver la foto subida")

print("== Docente: respuestas y nota del trabajo")
c, t, *_ = doc.get("/examenes/%s/resultados" % fid)
ok(
    'class="barra"' in t and "Tarde" in t and "1 respuesta" in t and "Hacerlo más rápido." in t and "corte.png" in t,
    "resumen con barras y respuestas de texto",
)
c, t, *_ = doc.get("/por-calificar")
ok("Trabajo: Ficha: mi primer corte" in t, "el trabajo aparece en Por calificar")
iid = ruta_f.rsplit("/", 1)[1]
c, t, *_ = doc.get("/intentos/" + iid)
ok("Calificar este trabajo" in t, "pantalla para calificar el trabajo")
c, t, *_ = doc.post("/intentos/%s/revisar" % iid, {"nota": "18", "comentario_general": "Muy buen trabajo", "siguiente": "0"})
ok("Revisión guardada" in t and "Nota 18" in t, "docente pone nota 18 al trabajo")
c, t, *_ = al.get("/intentos/" + iid)
ok("18" in t and "Muy buen trabajo" in t, "alumno ve nota y comentario")
c, t, h, raw = doc.get("/examenes/%s/descargar" % fid)
csvt = raw.decode("utf-8")
ok(
    "Tarde" in csvt and "Tijera; Otra: Secadora" in csvt and "Limpieza: Bien" in csvt and "18" in csvt,
    "descarga de respuestas para Excel",
)
c, t, h, raw = doc.get("/cursos/1/notas/excel")
ok("Trabajo: Ficha: mi primer corte" in raw.decode("utf-8"), "el trabajo entra al libro de notas")

print("== Encuesta (sin nota)")
c, t, *_ = doc.post(
    "/cursos/1/examenes",
    {"modo": "encuesta", "titulo": "Encuesta: ¿te gusta el aula?", "fecha": "2030-01-01", "hora": "23:59", "intentos_max": "1"},
)
eid = re.search(r'action="[^"]*/examenes/(\d+)/preguntas"', t).group(1)
doc.post(
    "/examenes/%s/preguntas" % eid,
    {"tipo": "escala", "enunciado": "¿Cuánto te gusta?", "escala_min": "1", "escala_max": "5", "obligatoria": "1"},
)
doc.post("/examenes/%s/publicar" % eid, {"publicar": "1"})
c, t, *_ = al.post("/examenes/%s/empezar" % eid)
pe = sql("SELECT id FROM av_preguntas WHERE cuestionario_id = %s" % eid)[0][0]
c, t, *_ = al.post(re.search(r'action="[^"]*(/intentos/\d+)"', t).group(1), {"txt[%s]" % pe: "5"})
ok("Gracias" in t and "Tu nota" not in t, "encuesta enviada, sin nota")
c, t, h, raw = doc.get("/cursos/1/notas/excel")
ok("Encuesta" not in raw.decode("utf-8"), "la encuesta no entra al promedio")

print("== Mensajes")
c, t, *_ = al.get("/cursos/1")
ok("Escribir a mi profesor" in t, 'curso tiene "Escribir a mi profesor"')
doc_id = re.search(r"/mensajes/con/1/(\d+)", t).group(1)
c, t, *_ = al.get("/mensajes/con/1/" + doc_id)
ok("Para:" in t and 'name="para"' in t and "Nuevo mensaje" in t, "sin conversación, abre el formulario de mensaje nuevo")
c, t, *_ = al.post("/mensajes/con/1/" + doc_id, {"texto": "Profesora, ¿mañana hay clase?"})
ok("mañana hay clase" in t and "Enviado" in t, "alumno envía mensaje")
conv = re.search(r'action="[^"]*/mensajes/(\d+)"', t).group(1)
c, t, *_ = doc.get("/")
ok("mensaje nuevo de tus alumnos" in t, "Inicio del docente avisa mensaje nuevo")
c, t, *_ = doc.get("/mensajes")
ok("1 mensaje nuevo" in t and "Nuevo mensaje" in t, "mensajes nivel 1: tarjeta del módulo con su mensaje nuevo")
c, t, *_ = doc.get("/mensajes/curso/1")
ok("1 sin leer" in t and "Quispe" in t and "Alumno" in t, "mensajes nivel 2: hilo con el alumno y mensajes sin leer")
c, t, *_ = doc.get("/mensajes/" + conv)
c, t, *_ = doc.post("/mensajes/" + conv, {"texto": "Sí, a las 8 de la mañana."})
ok("a las 8 de la mañana" in t, "docente responde")
c, t, *_ = al.get("/mensajes/" + conv)
ok("a las 8 de la mañana" in t and "Leído" in t, "alumno ve la respuesta y que su mensaje fue leído")
c, t, *_ = al.post("/mensajes/" + conv, {"texto": ""})
ok("antes de enviarlo" in t, "no envía mensaje vacío")
c, t, *_ = al2.get("/mensajes/" + conv, seguir=False)
ok(c == 403, "otro alumno no puede leer la conversación")
otro_doc = sql("SELECT docente_id FROM cursos WHERE id = 2")[0][0]
c, t, *_ = al.get("/mensajes/con/2/" + otro_doc, seguir=False)
ok(c == 403, "alumno no puede escribir al docente de otro curso")
c, t, *_ = adm.get("/mensajes", seguir=False)
ok(c == 403, "admin no usa mensajería privada")

print("== Salir")
c, t, *_ = doc.post("/salir")
ok("Cerraste sesión" in t, "cerrar sesión")

print()
print("FALLAS:", len(fallos))
for f in fallos:
    print(" -", f)
sys.exit(1 if fallos else 0)
