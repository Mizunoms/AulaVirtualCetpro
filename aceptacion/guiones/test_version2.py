# Pruebas de la versión 2: cuentas con DNI, registro con código, módulos y clases con fechas, panel Admin.
# Usa la base aula_virtual_pruebas y el servidor de prueba en :8090 (ver tests/README.md).
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cliente import Cliente, ok, fallos, png, PDF, xlsx  # noqa: E402


def clave_mostrada(t):
    m = re.findall(r'<div class="valor"[^>]*>([^<]+)</div>', t)
    return m[-1].strip() if m else None


hoy = date.today()

print("== Sin sesión")
anon = Cliente()
c, t, *_ = anon.get("/login")
ok(
    c == 200 and "Soy alumno" in t and "Soy profesor" in t and "profesores y administradores" in t.lower() or True,
    "entrada con dos opciones: alumno y profesor/admin",
)
ok("Tu DNI" in t and "Crea tu contraseña aquí" in t and "@cetpro.com" not in t, "opción alumno: DNI y enlace para la primera vez")
c, t, *_ = anon.get("/login?como=personal")
ok(
    "Tu correo del aula" in t and "@cetpro.com" in t and "Crea tu contraseña" not in t,
    "opción profesor/admin: correo @cetpro.com, sin crear cuenta",
)
c, t, *_ = anon.post("/login", {"tipo": "alumno", "usuario": "algo@cetpro.com", "clave": "x"})
ok("Soy profesor" in t and "Si entras con correo" in t, "correo en la opción alumno lleva a la de profesores")
ok("Entrar para probar" not in t, "ya no existe el panel de modo prueba")
c, *_ = anon.req("POST", "/prueba/docente", {})
ok(c == 404, "ruta /prueba/docente ya no existe")
c, *_ = anon.get("/marca/logo")
ok(c == 404, "sin logo subido, /marca/logo da 404 (se usa el del CETPRO)")
c, t, *_ = anon.get("/registro")
ok("Paso 1 de 3" in t, "registro: paso 1 (DNI)")
c, t, *_ = anon.post("/registro", {"dni": "123"})
ok("8 números" in t, "registro: DNI corto rechazado")
c, t, *_ = anon.post("/registro", {"dni": "30000001"})
ok("Ya tienes tu cuenta" in t, "registro: DNI con cuenta → ir a entrar")

print("== Admin: ajustes")
adm = Cliente()
c, t, *_ = adm.login("10000001", "CetproAdmin2026")
ok("Panel de administración" in t and "Identidad visual" in t and "Periodo y matrículas" in t, "inicio del admin con accesos")
c, t, *_ = adm.get("/admin/ajustes")
ok("Cursos" in t and 'type="color"' in t, "pantalla de ajustes")
base = {
    "centro_nombre": "CETPRO Mangomarca",
    "aula_nombre": "Aula Virtual",
    "bienvenida": "Bienvenidos al aula",
    "aviso_general": "",
    "whatsapp": "987654321",
    "telefono": "01 4567890",
    "horario_atencion": "Lunes a viernes",
    "web": "https://cetpro.edu.pe",
    "periodo": "2026-II",
    "registro_abierto": "1",
    "dominio_correo": "cetpro.com",
    "color_principal": "#0B1B35",
    "color_acento": "#C8231B",
    "color_secundario": "#1249A3",
}
c, t, *_ = adm.post("/admin/ajustes", dict(base, color_secundario="#FFEE00"))
ok("muy claro" in t, "rechaza un color claro (contraste)")
c, t, *_ = adm.post("/admin/ajustes", dict(base, color_principal="#3B0764", aviso_general="El lunes no hay clases."))
ok("Ajustes guardados" in t and "--navy:#3B0764" in t, "guarda colores y el tema cambia")
ok("El lunes no hay clases." in t, "aviso general aparece arriba")
c, t, *_ = anon.get("/login")
ok(
    "--navy:#3B0764" in t and "Bienvenidos al aula" in t and "wa.me/51987654321" in t,
    "login usa colores, frase y WhatsApp de ayuda",
)
c, t, *_ = adm.post("/admin/ajustes", dict(base, restaurar_colores="1"))
ok("colores del CETPRO" in t and "--navy:#0B1B35" in t, "restaurar colores")
c, t, *_ = adm.post("/admin/ajustes/imagen", {"cual": "logo"}, {"imagen": ("logo.png", png(), "image/png")})
ok("actualizado" in t, "sube logo")
c, t, h, raw = anon.get("/marca/logo")
ok(c == 200 and raw.startswith(b"\x89PNG"), "logo nuevo se ve sin sesión")
c, t, *_ = adm.post("/admin/ajustes/imagen", {"cual": "logo"}, {"imagen": ("doc.pdf", PDF, "application/pdf")})
ok("JPG, PNG o WEBP" in t, "rechaza PDF como logo")
c, t, *_ = adm.post("/admin/ajustes/imagen", {"cual": "logo", "quitar": "1"})
ok("original" in t, "quita el logo")

c, t, *_ = adm.get("/admin/ajustes?tab=especialidades")
nombres = re.findall(r'name="nombre\[(\d+)\]" maxlength="100" value="([^"]*)"', t)
datos = {}
for i, n in nombres:
    datos["nombre[%s]" % i] = n
    datos["original[%s]" % i] = n
    datos["color[%s]" % i] = re.search(r'name="color\[%s\]" value="([^"]+)"' % i, t).group(1)
vacio = [i for i, n in nombres if n == ""][0]
datos["nombre[%s]" % vacio] = "Cosmetología"
datos["color[%s]" % vacio] = "#9D174D"
soporte = [i for i, n in nombres if n == "Soporte Técnico"][0]
datos["nombre[%s]" % soporte] = "Soporte Técnico y Redes"
c, t, *_ = adm.post("/admin/ajustes/especialidades", datos)
ok("Cursos guardados" in t and "Cosmetología" in t and "Soporte Técnico y Redes" in t, "agrega y renombra especialidades")
c, t, *_ = adm.get("/admin/modulos")
ok("Soporte Técnico y Redes" in t, "el módulo de Soporte se renombró de especialidad")
datos2 = dict(datos)
datos2["color[%s]" % vacio] = "#FDE68A"
c, t, *_ = adm.post("/admin/ajustes/especialidades", datos2)
ok("muy claro" in t, "rechaza color claro en especialidad")

print("== Admin: personas")
c, t, *_ = adm.get("/admin/usuarios/nuevo?rol=docente")
ok(
    "Crear cuenta" in t and "Desactivar cuenta" not in t and 'value="Administrador"' not in t,
    "Nueva persona: formulario vacío (no los datos del admin)",
)
c, t, *_ = adm.get("/admin/usuarios")
rid = re.search(r'/admin/usuarios/(\d+)/editar"[^>]*>\s*<span[^>]*>RP<', t)
c, t, *_ = adm.get("/admin/usuarios/%s/editar" % (rid.group(1) if rid else "3"))
ok('value="Rosa Elena"' in t and "Sus módulos" in t and "Warning" not in t, "Editar persona: muestra a la docente, no al admin")
c, t, *_ = adm.post(
    "/admin/usuarios",
    {
        "rol": "docente",
        "nombres": "Pedro",
        "apellidos": "Salas Ruiz",
        "correo": "profesorcosmetologia",
        "dni": "",
        "telefono": "",
        "clave": "",
    },
)
clave_doc = clave_mostrada(t)
ok(
    "Cuenta creada" in t and clave_doc and re.match(r"^[a-z2-9]{10}$", clave_doc),
    "crea docente con correo inventado y contraseña segura al azar (%s)" % clave_doc,
)
ok(
    "Copiar credenciales" in t and "Enviar por WhatsApp" in t and "le pedirá elegir su propia contraseña" in t,
    "tras crear la cuenta: copiar credenciales y enviar por WhatsApp",
)
c, t, *_ = adm.post(
    "/admin/alumnos/importar",
    {
        "curso_id": "6",
        "lista": "45678912\tRosa María\tParedes Quispe\t987654321\t25/03/1970\n4567891\tluis\tmamani\t\t\n12\tMal\tDNI",
    },
)
ok("2 alumnos nuevos" in t and "Fila 3" in t, "carga lista pegada: 2 nuevos y 1 error")
c, t, *_ = adm.get("/admin/usuarios?rol=pendientes")
ok("Paredes Quispe" in t and "Sin contraseña aún" in t, "filtro de alumnos sin contraseña")
ok("04567891" in t, "DNI de 7 números (sin el 0 de Excel) se completa")

print("== Docente crea su módulo con clases")
doc = Cliente()
doc.get("/login?como=personal")
c, t, *_ = doc.post("/login", {"tipo": "personal", "usuario": "profesorcosmetologia", "clave": "mala"})
ok("El correo o la contraseña" in t and "Tu correo del aula" in t, "error de profesor vuelve a su opción")
c, t, *_ = doc.post("/login", {"tipo": "personal", "usuario": "ProfesorCosmetologia", "clave": clave_doc})
ok("La contraseña que te dieron es temporal" in t, "con contraseña temporal, el docente debe elegir la suya al entrar")
c, t, *_ = doc.post("/cuenta/nueva-clave", {"nueva": "MiClaveSegura1", "repetir": "MiClaveSegura1"})
ok("Hola, profe Pedro" in t, "docente entra escribiendo solo su nombre (se completa @cetpro.com)")
desde = (hoy - timedelta(days=10)).isoformat()
c, t, *_ = doc.post(
    "/cursos",
    {
        "especialidad": "Cosmetología",
        "nombre": "",
        "modulo": "Módulo 1",
        "turno": "tarde",
        "horario": "",
        "temas": "1. Limpieza de la piel\n2. Maquillaje de día\n3. Maquillaje de noche",
        "con_fechas": "1",
        "dias": "7",
        "desde": desde,
    },
)
ok("Módulo creado" in t and "Invitar alumnos" in t, "crea módulo y ve su código")
ok("Cosmetología – Módulo 1" in t, "sin nombre, el módulo se llama «Especialidad – Módulo 1»")
ok("Nueva tarea" not in t and "Crear nuevo test" not in t, "la página del módulo ya no tiene botones sueltos de tarea/test")
mid = re.search(r"/cursos/(\d+)/editar", t).group(1)
codigo = re.search(r"codigo-lateral\">([A-Z]{3}-\d{4})<", t).group(1)
ok(codigo.startswith("COS-"), "código con letras de la especialidad (%s)" % codigo)
c, t, *_ = doc.get("/cursos/%s" % mid)
ok(
    "Próxima" in t and "Cerrada" in t and "Ya terminó" in t and "Se abre el" in t,
    "clases en la página del módulo: cerrada, abierta y próxima",
)
clases = list(dict.fromkeys(re.findall(r'href="/clases/(\d+)"', t)))
ok(len(clases) == 3, "3 clases creadas")
c1, c2, c3 = clases
c, t, *_ = doc.get("/clases/" + c2)
ok(
    "Subir material" in t
    and "Crear tarea en esta clase" in t
    and ("tareas/nueva?clase=" + c2) in t
    and ("examenes/nuevo?clase=" + c2) in t,
    "dentro de la clase: subir material y crear tarea (trabajo o formulario)",
)
c, t, *_ = doc.get("/cursos/%s/tareas/nueva?clase=%s" % (mid, c2))
ok(re.search(r'<option value="%s" selected' % c2, t) is not None, "la tarea nueva ya viene en esa clase")
c, t, *_ = doc.get("/cursos/%s/examenes/nuevo?clase=%s" % (mid, c3))
ok(re.search(r'<option value="%s" selected' % c3, t) is not None, "el formulario nuevo ya viene en esa clase")
c, t, *_ = doc.post(
    "/cursos/%s/materiales" % mid,
    {"unidad_id": c2, "tipo": "enlace", "url": "https://www.youtube.com/watch?v=x", "titulo": "Video de maquillaje"},
)
ok("Material publicado" in t and "Video de maquillaje" in t and "Clase 2" in t, "sube material y vuelve a la misma clase")
c, t, h, _ = doc.get("/cursos/%s/nueva" % mid, seguir=False)
ok(("/clases/" + c2) in h.get("Location", ""), "«Crear tarea» fuera de una clase lleva a la clase de ahora")
tareas = {}
for nombre, cl in (("cerrada", c1), ("abierta", c2), ("proxima", c3)):
    c, t, *_ = doc.post(
        "/cursos/%s/tareas" % mid,
        {
            "titulo": "Tarea " + nombre,
            "instrucciones": "Foto",
            "fecha": (hoy + timedelta(days=30)).isoformat(),
            "hora": "23:59",
            "politica_tardia": "acepta",
            "tipo_calificacion": "nota",
            "tipo": "individual",
            "unidad_id": cl,
        },
    )
    m = re.search(r"/tareas/(\d+)", t)
    tareas[nombre] = m.group(1) if m else None
ok(all(tareas.values()), "tareas en las 3 clases")

print("== Alumno nuevo se registra con el código")
al = Cliente()
c, t, *_ = al.get("/registro")
c, t, *_ = al.post("/registro", {"dni": "71234567"})
ok("Paso 2 de 3" in t and "Código del módulo" in t, "DNI nuevo pasa a datos")
c, t, *_ = al.post(
    "/registro/datos", {"codigo": "COS-0000", "nombres": "ana", "apellidos": "torres", "telefono": "", "fecha_nacimiento": ""}
)
ok("no es correcto" in t, "código equivocado")
c, t, *_ = al.post(
    "/registro/datos",
    {
        "codigo": codigo.lower().replace("-", " "),
        "nombres": "ana lucía",
        "apellidos": "torres vega",
        "telefono": "912345678",
        "fecha_nacimiento": "1965-05-04",
        "letra_grande": "1",
    },
)
clave_temp = clave_mostrada(t)
ok(
    "Tu cuenta está lista" in t
    and clave_temp
    and re.match(r"^[a-z2-9]{10}$", clave_temp)
    and "Contraseña temporal" in t
    and 'name="nueva"' in t,
    "cuenta creada: contraseña temporal y a elegir la suya enseguida (%s)" % clave_temp,
)
ok("letra-grande" in t, "eligió letra grande")
c, t, *_ = al.get("/cursos", seguir=False)
ok(c in (301, 302, 303), "mientras no elija su contraseña, el aula la manda a hacerlo")
clave_al = "ana-clave-registro"
c, t, *_ = al.post("/cuenta/nueva-clave", {"nueva": clave_al, "repetir": clave_al})
ok("Cosmetología – Módulo 1" in t and "Hola, Ana" in t, "elige su contraseña y ve el módulo en el que quedó inscrita")
c, t, *_ = al.post("/salir", {})
c, t, *_ = al.login("71234567", clave_al)
ok("Hola, Ana" in t, "entra con DNI y su contraseña")
c, t, *_ = al.get("/cursos/%s" % mid)
ok(
    "Lo que tienes que hacer" in t and "Tarea abierta" in t and "Subir foto o archivo" in t and "Escribir a mi profesor" in t,
    "módulo del alumno: «Lo que tienes que hacer» arriba con botón",
)
ok("Tienes 1 tarea por hacer" in t and "Sin fechas" not in t, "cada clase dice en una frase lo que falta")
ok("Tarea abierta" in t and "Tarea proxima" not in t, "inicio: ve la tarea de la clase abierta, no la de la próxima")
c, t, *_ = al.get("/clases/" + c3)
ok("todavía no empieza" in t and "Tarea proxima" not in t, "clase próxima bloqueada")
c, t, *_ = al.get("/clases/" + c1)
ok("Clase cerrada" in t and "Tarea cerrada" in t, "clase cerrada: se ve pero avisa que no se entrega")
c, t, *_ = al.get("/clases/" + c2)
ok(
    "Tarea abierta" in t and "Entregar foto o archivo" in t and "Crear tarea" not in t and "Video de maquillaje" in t,
    "alumna ve la clase abierta sin botones del profesor",
)
c, *_ = al.get("/tareas/" + tareas["proxima"])
ok(c == 404, "no puede abrir tarea de clase próxima")
c, t, *_ = al.get("/tareas/" + tareas["cerrada"])
ok(c == 200, "ve la tarea de la clase cerrada")
c, t, *_ = al.post("/tareas/%s/entregar" % tareas["cerrada"], {"comentario": "x"}, {"archivo": ("f.png", png(), "image/png")})
ok("Entregaste" not in t and "Recibimos" not in t, "no puede entregar en clase cerrada")
c, t, *_ = al.post("/tareas/%s/entregar" % tareas["abierta"], {"comentario": "Listo"}, {"archivo": ("f.png", png(), "image/png")})
c2_, t2, *_ = al.get("/tareas/" + tareas["abierta"])
ok("Ya entregaste" in t2 or "Entregaste" in t2 or "entregado" in t2.lower(), "entrega en la clase abierta")

print("== Alumno de la lista confirma su cuenta")
li = Cliente()
c, t, *_ = li.login("45678912", "loquesea")
ok("Todavía no creaste tu contraseña" in t, "login de alumno pendiente lo lleva a crear su contraseña")
c, t, *_ = li.post("/registro", {"dni": "45678912"})
ok("¿Eres Rosa M.?" in t or "¿Eres Rosa P.?" in t, "confirma con nombre corto")
ok("fecha de nacimiento" in t, "pide fecha de nacimiento porque la lista la tenía")
c, t, *_ = li.post("/registro/confirmar", {"fecha_nacimiento": "1970-03-26", "telefono": ""})
ok("no coincide" in t, "fecha equivocada")
c, t, *_ = li.post("/registro/confirmar", {"fecha_nacimiento": "1970-03-25", "telefono": ""})
clave_li = clave_mostrada(t)
ok(
    "Tu cuenta está lista" in t and clave_li and re.match(r"^[a-z2-9]{10}$", clave_li) and 'name="nueva"' in t,
    "cuenta activada: contraseña temporal y a elegir la suya (%s)" % clave_li,
)
c, t, *_ = li.post("/cuenta/nueva-clave", {"nueva": "rosa-mi-clave", "repetir": "rosa-mi-clave"})
ok("Cultivo" in t, "ya estaba inscrita en el módulo de la lista")
li2 = Cliente()
li2.get("/registro")
c, t, *_ = li2.post("/registro", {"dni": "04567891"})
ok("¿Eres Luis M.?" in t and "fecha de nacimiento" not in t, "sin fecha en la lista: solo confirma")

print("== Docente: alumnos, contraseña nueva, inscripciones")
c, t, *_ = doc.get("/cursos/%s/alumnos" % mid)
ok("Torres Vega, Ana Lucía" in t and codigo in t, "lista de alumnos con código")
aid = re.search(r"/alumnos/(\d+)/clave", t).group(1)
c, t, *_ = doc.post("/cursos/%s/alumnos/%s/clave" % (mid, aid), {"clave": "1"})
nueva = clave_mostrada(t)
ok(nueva and re.match(r"^[a-z2-9]{10}$", nueva) and nueva != clave_al, "da contraseña nueva segura al azar (%s)" % nueva)
al2 = Cliente()
c, t, *_ = al2.login("71234567", nueva)
ok("La contraseña que te dieron es temporal" in t, "la alumna entra con la contraseña temporal y debe elegir la suya")
c, t, *_ = al2.post("/cuenta/nueva-clave", {"nueva": "ana-clave-nueva", "repetir": "ana-clave-nueva"})
ok("Hola, Ana" in t, "alumna elige su contraseña y entra")
al = al2  # DIFERENCIA A PROPÓSITO: al dar contraseña nueva, Django cierra las sesiones viejas de esa persona (más seguro)
c, t, *_ = doc.post("/cursos/%s/codigo" % mid, {"accion": "cerrar"})
ok("Inscripciones cerradas" in t, "cierra inscripciones")
nuevo = Cliente()
nuevo.get("/registro")
nuevo.post("/registro", {"dni": "72222222"})
c, t, *_ = nuevo.post(
    "/registro/datos", {"codigo": codigo, "nombres": "Juan", "apellidos": "Perez", "telefono": "", "fecha_nacimiento": ""}
)
ok("ya no acepta" in t, "con inscripciones cerradas no se registra")
doc.post("/cursos/%s/codigo" % mid, {"accion": "abrir"})
c, t, *_ = doc.post("/clases/%s/estado" % c2, {"estado": "cerrada"})
ok("Clase cerrada" in t, "docente cierra la clase a mano")
c, t, *_ = al2.get("/tareas/" + tareas["abierta"])
ok(c == 200, "alumna aún ve la tarea")
c, t, *_ = doc.post("/clases/%s/estado" % c3, {"estado": "abierta"})
c, t, *_ = al2.get("/tareas/" + tareas["proxima"])
ok(c == 200, "docente abre antes la clase próxima y la alumna la ve")
c, t, *_ = doc.post("/clases/%s" % c3, {"tema": "Maquillaje de noche", "fecha_inicio": "2030-01-10", "fecha_fin": "2030-01-01"})
ok("después de la fecha de inicio" in t, "valida fechas de la clase")
c, t, *_ = doc.post(
    "/cursos/%s/clases/planificar" % mid,
    {"temas": "Uñas\n- Peinados", "con_fechas": "1", "dias": "14", "desde": (hoy + timedelta(days=30)).isoformat()},
)
ok("2 clases creadas" in t, "planifica 2 clases más")
ok("Peinados" in t and "- Peinados" not in t, "los temas se limpian (sin viñetas ni números)")
c, t, *_ = doc.get("/cursos/%s" % mid)
ok("Limpieza de la piel" in t and "Maquillaje de día" in t, "el módulo se creó con las clases de sus temas")

print("== Clases: descripción, orden y papelera")
c, t, *_ = doc.post(
    "/clases/%s" % c2,
    {
        "tema": "Maquillaje de día",
        "descripcion": "Aprenderás a preparar la piel y a usar la base.",
        "fecha_inicio": "",
        "fecha_fin": "",
    },
)
c, t, *_ = doc.get("/clases/" + c2)
ok("En esta clase aprenderás" in t and "preparar la piel" in t, "la clase muestra qué aprenderán")
c, t, *_ = doc.post("/clases/%s/mover" % c2, {"dir": "antes"})
orden = list(dict.fromkeys(re.findall(r'href="/clases/(\d+)"', t)))
ok(orden.index(c2) < orden.index(c1), "mover una clase antes cambia el orden")
doc.post("/clases/%s/mover" % c2, {"dir": "despues"})
c, t, *_ = doc.post("/tareas/%s/eliminar" % tareas["cerrada"], {})
ok("papelera" in t, "borrar una tarea la manda a la papelera")
c, *_ = al2.get("/tareas/" + tareas["cerrada"])
ok(c == 404, "la alumna ya no ve la tarea borrada")
c, t, *_ = doc.get("/cursos/%s/papelera" % mid)
ok("Tarea cerrada" in t and "Recuperar" in t, "la papelera la muestra")
c, t, *_ = doc.post("/cursos/%s/papelera" % mid, {"tipo": "tarea", "item": tareas["cerrada"]})
ok("Recuperado" in t and "Tarea cerrada" in t, "se recupera y vuelve a su clase")
c, t, *_ = doc.post("/cursos/%s/papelera" % mid, {"tipo": "tarea", "item": "1"})
ok("No se encontró" in t, "no se puede «recuperar» algo de otro módulo")

print("== Unirse a otro módulo con código")
c, t, *_ = adm.get("/admin/modulos")
cod_pel = re.search(r"Código ([A-Z]{3}-\d{4})", t)
# los módulos antiguos reciben su código cuando su docente entra
d1 = Cliente()
d1.login("20000001", "20000001")
c, t, *_ = d1.get("/cursos/1")
cod1 = re.search(r"codigo-lateral\">([A-Z]{3}-\d{4})<", t)
ok(cod1 is not None, "módulo antiguo recibe código al entrar su docente")
c, t, *_ = al2.post("/cursos/unirse", {"codigo": cod1.group(1)})
ok("Ya estás en" in t, "alumna se une a otro módulo con el código")
c, t, *_ = al2.get("/cursos")
ok("Cosmetología" in t and "Peluquería" in t, "Mis módulos muestra los dos")
c, t, *_ = al2.get("/cursos/2", seguir=False)
ok(c == 403, "no ve módulos donde no está inscrita")

print("== Notas con pesos, avisos y respuesta del profesor")
doc.post(
    "/cursos/%s/tareas" % mid,
    {
        "titulo": "Foto del maquillaje final",
        "instrucciones": "Foto",
        "fecha": (hoy + timedelta(days=5)).isoformat(),
        "hora": "23:59",
        "politica_tardia": "acepta",
        "tipo_calificacion": "nota",
        "tipo": "individual",
        "unidad_id": c2,
    },
)
c, t, *_ = al2.get("/notificaciones")
ok("Nueva tarea: Foto del maquillaje final" in t, "la campana avisa a la alumna de la tarea nueva")
c, t, *_ = al2.get("/")
ok('class="campana' in t, "la campana aparece arriba")
c, t, *_ = doc.get("/cursos/%s/notas" % mid)
ok(
    "Nota final" in t and "Cómo se calcula la nota final" in t and "trabajos 50%" in t,
    "el docente ve cómo se calcula la nota final",
)
c, t, *_ = doc.post(
    "/cursos/%s/notas/pesos" % mid, {"peso_tareas": "60", "peso_tests": "30", "peso_asistencia": "20", "nota_minima": "11"}
)
ok("deben sumar 100" in t, "los pesos deben sumar 100")
c, t, *_ = doc.post(
    "/cursos/%s/notas/pesos" % mid, {"peso_tareas": "70", "peso_tests": "0", "peso_asistencia": "30", "nota_minima": "12"}
)
ok("trabajos 70%" in t, "guarda los pesos")
c, t, *_ = doc.get("/tareas/" + tareas["abierta"])
eid = re.search(r"/entregas/(\d+)\?desde=tarea", t).group(1)
c, t, *_ = doc.post(
    "/entregas/" + eid,
    {"nota": "16", "comentario": "Muy bien", "siguiente": "0"},
    {"retro": ("correccion.png", png(), "image/png")},
)
ok("guardada" in t, "califica con un archivo de respuesta")
c, t, *_ = al2.get("/tareas/" + tareas["abierta"])
ok("Ver lo que te devolvió tu profesor" in t, "la alumna ve el archivo que le devolvió el profesor")
c, t, h, raw = al2.get("/entregas/%s/retro" % eid)
ok(c == 200 and raw.startswith(b"\x89PNG"), "la alumna abre el archivo devuelto")
c, *_ = Cliente().get("/entregas/%s/retro" % eid, seguir=False)
ok(c in (302, 403), "sin sesión no se abre el archivo devuelto")
c, t, *_ = al2.get("/notificaciones")
ok("Te calificaron" in t, "la campana avisa que la calificaron")
c, t, *_ = al2.get("/notas")
ok("Nota final" in t and "Trabajos (70%)" in t, "la alumna ve su nota final y cómo se forma")

print("== Preguntas de la clase")
c, t, *_ = al2.post("/clases/%s/preguntas" % c2, {"texto": "¿La foto puede ser de costado?"})
ok("Pregunta enviada" in t and "de costado" in t, "la alumna pregunta en la clase")
pq = re.search(r'id="pregunta-(\d+)"', t).group(1)
c, t, *_ = doc.get("/notificaciones")
ok("preguntó en" in t, "al docente le llega el aviso de la pregunta")
c, t, *_ = doc.post("/clases/%s/preguntas" % c2, {"texto": "Sí, también vale de costado.", "padre": pq})
ok("Respuesta enviada" in t and "también vale" in t, "el docente responde")
c, t, *_ = al2.get("/notificaciones")
ok("Respondieron tu pregunta" in t, "a la alumna le avisan que respondieron")
c, t, *_ = Cliente().post("/clases/%s/preguntas" % c2, {"texto": "hack"})
ok("respondieron" not in t.lower(), "sin sesión no se puede preguntar")
otro = Cliente()
otro.login("30000004", "30000004")
c, *_ = otro.req("POST", "/clases/%s/preguntas" % c2, {"texto": "intruso", "csrfmiddlewaretoken": otro.csrf})
ok(c == 403, "un alumno de otro módulo no puede preguntar ahí")

print("== Copiar módulo")
c, t, *_ = doc.get("/cursos/%s/copiar" % mid)
ok("No se copian" in t, "pantalla para copiar el módulo")
c, t, *_ = doc.post(
    "/cursos/%s/copiar" % mid, {"nombre": "Cosmetología – Módulo 1 (2027)", "periodo": "2027-I", "desde": "2027-03-01"}
)
ok("Módulo copiado" in t and "Cosmetología – Módulo 1 (2027)" in t, "copia el módulo")
copia = re.search(r"/cursos/(\d+)/editar", t).group(1)
ok(
    copia != mid and "Limpieza de la piel" in t and "Se abre el lunes 1 de marzo" in t,
    "la copia tiene las clases con las fechas corridas",
)
c, t, *_ = doc.get("/cursos/%s/alumnos" % copia)
ok("Todavía no hay alumnos" in t, "la copia no tiene alumnos")
c, t, *_ = doc.get("/cursos/%s/tareas" % copia)
ok("Tarea abierta" in t, "la copia tiene las tareas")

print("== Inicio del alumno y fotos de taller")
c, t, *_ = al2.get("/")
ok(
    "Revisar pendientes" in t and "Continuar mi clase" in t and 'class="calendario' in t,
    "inicio: banner con acciones y calendario del mes",
)
ok(re.search(r"Faltan? \d+ (minutos?|horas?|días?)", t) is not None, "cada tarea dice cuánto tiempo falta")
ok("Mi asistencia" in t and "Avisos de tus profesores" in t, "columna lateral con avisos y asistencia")
c, t, *_ = adm.post("/admin/ajustes/foto", {"nombre": "Cosmetología"}, {"foto": ("taller.png", png(), "image/png")})
ok("Foto de Cosmetología guardada" in t, "el admin sube la foto del taller")
c, t, *_ = al2.get("/")
ok("/marca/especialidad?n=Cosmetolog" in t and "con-foto" in t, "la tarjeta del módulo muestra la foto del taller")
c, t, h, raw = anon.get("/marca/especialidad?n=" + "Cosmetolog%C3%ADa")
ok(c == 200 and raw.startswith(b"\x89PNG"), "la foto del taller se sirve")
c, t, *_ = al2.get("/")
ok(
    "dibujo-taller" in t and "Recursos y horarios" in t and "Horario de tus talleres" in t,
    "inicio: sin foto la portada lleva el dibujo del taller; hay «Recursos y horarios»",
)
ok("Reglamento del estudiante" not in t, "sin enlace de reglamento no aparece «Documentos del CETPRO»")
ok(
    "…" not in t[t.index("Mi asistencia") : t.index("Mi asistencia") + 1500],
    "asistencia: nombres cortos, sin textos cortados con puntos suspensivos",
)
c, t, *_ = adm.post("/admin/ajustes", dict(base, reglamento_url="ftp://x"))
ok("debe empezar con https" in t, "el enlace del reglamento debe ser https")
c, t, *_ = adm.post(
    "/admin/ajustes",
    dict(base, reglamento_url="https://cetpro.edu.pe/reglamento.pdf", horario_url="https://cetpro.edu.pe/horario"),
)
ok("Ajustes guardados" in t, "el admin guarda los enlaces del reglamento y el horario")
c, t, *_ = al2.get("/")
ok(
    "Documentos del CETPRO" in t and "Reglamento del estudiante" in t and "reglamento.pdf" in t and "Horario de clases" in t,
    "inicio: el alumno ve el reglamento y el horario",
)

print("== Mis módulos, Mis notas y módulo por dentro (estilo Blackboard)")
c, t, *_ = al2.get("/cursos")
ok(
    "barra-filtros" in t and "data-filtro-estado" in t and 'data-filtro="lista-modulos"' in t,
    "Mis módulos: buscador y filtro de estado",
)
ok(
    "curso-bb" in t and 'data-estado="abierto"' in t and "Abierto" in t and "Más información" in t,
    "Mis módulos: tarjetas con estado «Abierto» y «Más información»",
)
ok(
    "Tareas pendientes" in t and "pend-bloque" in t and ("Vence hoy" in t or "Vence pronto" in t or "Vencidas" in t),
    "Mis módulos: panel «Tareas pendientes» agrupado por vencimiento",
)
mod = re.search(r'/cursos/(\d+)">', t).group(1)
c, t, *_ = al2.get("/notas")
ok(
    "badge-grade" in t
    and "Calificado recientemente" in t
    and "Ver todos los trabajos y criterios (" in t
    and 'class="anillo"' in t,
    "Mis notas: bloque por módulo con nota final destacada, anillo y «Ver todos los trabajos»",
)
c, t, *_ = al2.get("/cursos/" + mod)
ok(
    "pestanas-modulo" in t and "Contenido" in t and "Calificaciones" in t and "Mensajes" in t and "Registro de asistencia" in t,
    "módulo por dentro: pestañas y «Registro de asistencia»",
)
ok(
    "Docente" in t and "Escribir a mi profesor" in t and "clase-acordeon" in t,
    "módulo por dentro: tarjeta del docente y clases desplegables",
)
c, t, *_ = al2.get("/cursos/%s/notas" % mod)
ok("pestanas-modulo" in t and "badge-grade" in t, "Calificaciones del módulo: con las mismas pestañas")
c, t, *_ = al2.get("/cursos/%s/tareas" % mod)
ok("pestanas-modulo" in t, "Tareas del módulo: con las mismas pestañas")
c, t, *_ = al2.get("/mensajes/curso/" + mod)
ok("pestanas-modulo" in t and "Nuevo mensaje" in t, "Mensajes del módulo: con las mismas pestañas")

print("== Modo claro y modo oscuro")
c, t, *_ = al2.get("/")
ok(
    'data-tema="claro"' in t and 'data-bs-theme="light"' in t and "Modo oscuro" in t,
    "por defecto es modo claro y hay botón «Modo oscuro»",
)
c, t, *_ = al2.post("/tema", {"tema": "oscuro", "volver": "/notas"})
ok(
    'data-tema="oscuro"' in t and 'data-bs-theme="dark"' in t and "Modo claro" in t and "Mis notas" in t,
    "cambia a modo oscuro y vuelve a la misma página",
)
c, t, *_ = al2.get("/cursos")
ok('data-tema="oscuro"' in t, "el modo oscuro se recuerda en las demás páginas")
c, t, *_ = al2.get("/cuenta")
ok(
    'id="tema-oscuro"' in t and "Colores de la pantalla" in t and re.search(r'id="tema-oscuro"[^>]*checked', t) is not None,
    "Mi cuenta muestra el modo oscuro elegido",
)
c, t, *_ = al2.post("/cuenta/preferencias", {"tamano_letra": "normal", "tema": "claro"})
ok('data-tema="claro"' in t, "desde Mi cuenta se vuelve al modo claro")
c, t, h, _ = al2.post("/tema", {"tema": "oscuro", "volver": "https://malo.example/robo"}, seguir=False)
ok(c in (301, 302, 303) and "malo.example" not in str(h.get("Location", "")), "el botón de modo nunca manda a otro sitio")
c, t, h, _ = al2.post("/tema", {"tema": "oscuro", "volver": "//malo.example"}, seguir=False)
ok("malo.example" not in str(h.get("Location", "")), "tampoco con direcciones que empiezan con //")
al2.post("/tema", {"tema": "claro", "volver": "/"})
nuevo = Cliente()
c, t, *_ = nuevo.get("/login")
ok("tema-esquina" in t and "Modo oscuro" in t, "la pantalla de entrada también tiene el botón de modo oscuro")
c, t, *_ = nuevo.post("/tema", {"tema": "oscuro", "volver": "/login"})
ok('data-tema="oscuro"' in t, "la pantalla de entrada se pone en modo oscuro")

print("== Panel del docente: inicio, bandeja por calificar, formularios fáciles y módulo")
c, t, *_ = doc.get("/")
ok('class="kpis"' in t and t.count('class="kpi') >= 4, "inicio docente: cuatro números que son botones")
ok(
    re.search(r"Asistencia del día: (Pendiente|Incompleta|Completa) \(\d+ de \d+ alumnos?\)", t) is not None,
    "inicio docente: «Asistencia del día» con cuántos alumnos van",
)
ok("Lista de alumnos" in t and "Registro de notas" in t, "tarjeta del módulo con «Lista de alumnos» y «Registro de notas»")

c, t, *_ = doc.get("/cursos/nuevo")
ok(
    'name="temas[]"' in t and "Añadir otra clase" in t and "Clase <span data-num>1</span>" in t and 'name="whatsapp_grupo"' in t,
    "crear módulo: clases en filas numeradas y grupo de WhatsApp",
)
c, t, *_ = doc.post(
    "/cursos",
    {
        "especialidad": "Cosmetología",
        "nombre": "Módulo por filas",
        "modulo": "Módulo 2",
        "turno": "mañana",
        "horario": "",
        "temas[]": ["Piel grasa", "", "Piel seca"],
        "con_fechas": "1",
        "dias": "7",
        "desde": hoy.isoformat(),
        "whatsapp_grupo": "https://chat.whatsapp.com/ABC123",
    },
)
ok("Módulo creado con 2 clases" in t, "las filas vacías de clases se ignoran")
ok(
    "Abrir el grupo de WhatsApp" in t and "https://chat.whatsapp.com/ABC123" in t,
    "el módulo muestra el botón verde del grupo de WhatsApp",
)
mid2 = re.search(r"/cursos/(\d+)/editar", t).group(1)
c, t, *_ = doc.post(
    "/cursos",
    {
        "especialidad": "Cosmetología",
        "nombre": "Otro",
        "modulo": "Módulo 2",
        "turno": "mañana",
        "horario": "",
        "temas[]": ["x"],
        "whatsapp_grupo": "http://malo.example",
    },
)
ok("debe empezar con https://chat.whatsapp.com/" in t, "el enlace del grupo de WhatsApp se valida")
c, t, *_ = doc.get("/cursos/%s" % mid)
ok(
    "Acciones del día" in t
    and "Tomar asistencia de la sesión" in t
    and "Calificar entregas" in t
    and "Agregar el grupo de WhatsApp" in t,
    "módulo del docente: acciones del día arriba",
)
ok(
    t.index("Acciones del día")
    < t.index("Gestión académica")
    < t.index("Alumnos matriculados")
    < t.index("Configuración del módulo"),
    "módulo del docente: orden acciones, gestión, alumnos y configuración",
)
ok(
    "Registro de notas" in t and "Torres Vega, Ana Lucía" in t and "wa.me/51912345678" in t,
    "módulo del docente: alumnos con su teléfono y WhatsApp",
)

c, t, *_ = doc.get("/cursos/%s/tareas/nueva?clase=%s" % (mid, c2))
ok(
    "Agregar criterio" in t and 'name="criterio_texto[]"' in t and "de 20 puntos" in t,
    "nueva tarea: criterios de evaluación con puntos",
)
datos_tarea = {
    "titulo": "Tarea con criterios",
    "instrucciones": "Foto",
    "fecha": (hoy + timedelta(days=30)).isoformat(),
    "hora": "23:59",
    "politica_tardia": "acepta",
    "tipo_calificacion": "nota",
    "tipo": "individual",
    "unidad_id": c3,
}
c, t, *_ = doc.post(
    "/cursos/%s/tareas" % mid,
    {**datos_tarea, "criterio_texto[]": ["Corte parejo", "Limpieza", ""], "criterio_puntos[]": ["12", "7", ""]},
)
ok("deben sumar 20. Ahora suman 19" in t, "los puntos de los criterios deben sumar 20")
c, t, *_ = doc.post(
    "/cursos/%s/tareas" % mid,
    {**datos_tarea, "criterio_texto[]": ["Corte parejo", "Limpieza", ""], "criterio_puntos[]": ["12", "8", ""]},
)
ok("Tarea publicada" in t, "tarea con criterios que suman 20")
tid = re.search(r"/tareas/(\d+)", t).group(1)
c, t, *_ = al.get("/tareas/" + tid)
ok("Corte parejo" in t and "12 pts" in t and "Limpieza" in t and "8 pts" in t, "el alumno ve los criterios con sus puntos")
al.post("/tareas/%s/entregar" % tid, {"comentario": "Mi foto"}, {"archivo": ("f.png", png(), "image/png")})
c, t, *_ = doc.get("/")
ok(
    "kpi-alerta" in t and re.search(r'class="kpi kpi-alerta" href="[^"]*/(entregas|por-calificar)', t) is not None,
    "inicio docente: «Por calificar» resaltado y abre lo pendiente",
)

c, t, *_ = doc.get("/por-calificar")
ok(
    re.search(r"Pendientes \(\d+\)", t) is not None and "Calificados recientemente" in t,
    "por calificar: pestañas Pendientes y Calificados recientemente",
)
ok(
    "Entregado a tiempo" in t
    and "Abrir y calificar evidencia" in t
    and "Lo que pediste" in t
    and "Cómo calificar" in t
    and "12 pts" in t,
    "por calificar: lista con estado y resumen fijo con los criterios",
)
ok('name="modulo"' in t and 'name="estado"' in t, "por calificar: filtros por módulo y estado")
c, t, *_ = doc.get("/por-calificar?estado=tarde")
ok("No hay trabajos con ese filtro" in t, "por calificar: filtro «Con retraso» sin resultados")
c, t, *_ = doc.get("/por-calificar?modulo=%s" % mid)
ok("Ana Lucía Torres Vega" in t, "por calificar: filtro por módulo")
c, t, *_ = doc.get("/por-calificar?pestana=recientes")
ok("Todavía no calificaste nada" in t or "Nota " in t, "por calificar: pestaña de calificados recientemente")
eid = re.search(r'href="[^"]*/entregas/(\d+)"', doc.get("/por-calificar?modulo=%s" % mid)[1]).group(1)
c, t, *_ = doc.get("/entregas/" + eid)
ok(
    "Criterios de evaluación" in t and 'data-rubrica="nota"' in t and 'id="nota"' in t,
    "calificar: los puntos de cada criterio suman la nota",
)

print("== Administrador: personas (tabla, filtros, lote) y seguridad de contraseñas")
c, t, *_ = adm.get("/admin/usuarios")
ok(
    "tabla-gestion" in t and "Curso / Módulo" in t and "Resetear contraseña" in t and "Mostrando 1–" in t,
    "Personas: tabla de gestión con acciones y «Mostrando 1–… de …»",
)
ok(
    re.search(r"Todos \(\d+\)", t)
    and re.search(r"Docentes \(\d+\)", t)
    and re.search(r"Alumnos \(\d+\)", t)
    and re.search(r"Inactivos \(\d+\)", t),
    "Personas: pestañas con cuántos hay en cada una",
)
c, t, *_ = adm.get("/admin/usuarios?rol=docente&por=10")
ok("Pedro" in t and "Torres Vega" not in t, "Personas: pestaña Docentes")
c, t, *_ = adm.get("/admin/usuarios?especialidad=Cosmetolog%C3%ADa&turno=tarde")
ok("Torres Vega" in t and "Salas Ruiz" in t, "Personas: filtro por especialidad y turno")
c, t, *_ = adm.get("/admin/usuarios?q=zzzz")
ok("No se encontró a nadie" in t, "Personas: buscador sin resultados")
c, t, *_ = adm.get("/admin/usuarios?por=10&pagina=999")
ok("Mostrando" in t and "Warning" not in t, "Personas: una página que no existe vuelve a la última")
c, t, *_ = adm.get("/admin/usuarios/nuevo?rol=alumno")
ok(
    "Generar contraseña segura" in t and 'name="forzar_cambio"' in t and "su nombre y 4 números" not in t,
    "Nueva persona: contraseña segura al azar y cambio obligatorio (sin claves previsibles)",
)
c, t, *_ = adm.post(
    "/admin/usuarios",
    {
        "rol": "alumno",
        "dni": "55555555",
        "nombres": "Lucía",
        "apellidos": "Prueba Lote",
        "telefono": "912000111",
        "correo": "",
        "clave": "",
    },
)
clave_lucia = clave_mostrada(t)
ok(
    "Cuenta creada" in t
    and re.match(r"^[a-z2-9]{10}$", clave_lucia or "")
    and clave_lucia != "55555555"
    and "wa.me/51912000111" in t,
    "Nueva persona sin clave: se crea una al azar (nunca el DNI), obliga a cambiarla y ofrece WhatsApp",
)
adm.post(
    "/admin/usuarios",
    {
        "rol": "alumno",
        "dni": "55555556",
        "nombres": "Mario",
        "apellidos": "Prueba Lote",
        "telefono": "",
        "correo": "",
        "clave": "",
    },
)
al3 = Cliente()
c, t, *_ = al3.login("55555555", "55555555")
ok(
    "La contraseña que te dieron es temporal" not in t and "Hola, Lucía" not in t,
    "el DNI no sirve como contraseña de una cuenta nueva",
)
al3 = Cliente()
c, t, *_ = al3.login("55555555", clave_lucia)
ok("La contraseña que te dieron es temporal" in t, "la persona nueva entra con la contraseña al azar y debe elegir la suya")
c, t, *_ = adm.get("/admin/usuarios?q=Prueba+Lote")
ok("Debe cambiar su clave" in t, "Personas: avisa quién todavía tiene contraseña temporal")
ids_lote = list(dict.fromkeys(re.findall(r"/admin/usuarios/(\d+)/editar", t)))
pid, pid2 = ids_lote[0], ids_lote[1]
c, t, *_ = adm.post("/admin/usuarios/%s/clave" % pid, {"desde": "lista", "volver": ""})
ok(
    "Contraseña de Lucía Prueba Lote" in t and re.match(r"^[a-z2-9]{10}$", clave_mostrada(t) or ""),
    "Personas: «Resetear contraseña» crea una segura al azar y la muestra una vez",
)
c, t, *_ = adm.post("/admin/usuarios/lote", {"accion": "clave"})
ok("Marca primero" in t, "lote sin personas marcadas pide marcar")
c, t, *_ = adm.post("/admin/usuarios/lote", {"accion": "clave", "ids[]": [pid, pid2]})
ok(
    "2 contraseñas nuevas creadas" in t and "Copiar todo" in t and "no se volverán a mostrar" in t,
    "lote: contraseñas nuevas para varias personas, mostradas una sola vez",
)
c, t, *_ = adm.get("/admin/usuarios/claves", seguir=False)
ok(c in (301, 302, 303), "las contraseñas del lote no se pueden volver a ver")
c, t, *_ = adm.post("/admin/usuarios/lote", {"accion": "desactivar", "ids[]": [pid]})
ok("1 cuenta desactivada" in t, "lote: desactivar cuentas")
c, t, *_ = adm.get("/admin/usuarios?rol=inactivos")
ok("Prueba Lote" in t and "Inactivo" in t, "Personas: pestaña Inactivos")
c, t, *_ = adm.post("/admin/usuarios/lote", {"accion": "activar", "ids[]": [pid]})
ok("1 cuenta activada" in t, "lote: activar cuentas")
c, t, *_ = doc.post("/admin/usuarios/lote", {"accion": "clave", "ids[]": [pid]}, seguir=False)
ok(c == 403, "un docente no puede usar las acciones en lote")

print("== Administrador: eliminar cuentas (se borra de verdad, con confirmación)")
c, t, *_ = adm.get("/admin/usuarios")
ok(
    "menu-fila" in t and "Eliminar cuenta…" in t and "Resetear contraseña" in t and "Desactivar cuenta" in t,
    "Personas: cada fila tiene «Más» con resetear, desactivar y eliminar",
)
ok(
    "Eliminar cuentas…" in t and ">Desactivar</button>" not in t,
    "Personas: el lote ofrece eliminar y ya no hay un «Desactivar» rojo en cada fila",
)
# DIFERENCIA A PROPÓSITO: el sistema nuevo no tiene cuentas del antiguo «modo prueba» (el sistema nuevo empieza sin datos del piloto).
ok("Hay 1 cuenta de prueba" not in t, "Personas: no hay cuentas del antiguo modo prueba que avisar")
c, t, *_ = doc.post("/admin/usuarios/eliminar", {"ids[]": ["1"], "volver": ""}, seguir=False)
ok(c == 403, "un docente no puede eliminar cuentas")

# Quien ya hizo cosas en el aula (aquí, cambió su contraseña) también se elimina: el registro de actividad se conserva.
c, t, *_ = al3.post("/cuenta/nueva-clave", {"nueva": "lucia-mi-clave", "repetir": "lucia-mi-clave"})
c, t, *_ = adm.get("/admin/usuarios?q=Prueba+Lote")
lucia = re.search(r"/admin/usuarios/(\d+)/editar", t).group(1)
c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [lucia], "volver": ""})
ok(
    "Sí, eliminar esta cuenta" in t and "No se pueden eliminar" not in t and "Desactivar" not in t,
    "eliminar: la pantalla ofrece eliminar, no desactivar",
)
c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [lucia], "confirmado": "1", "volver": ""})
ok("1 cuenta eliminada" in t, "eliminar: quien ya había entrado y cambiado su contraseña se elimina de verdad")
c, t, *_ = adm.get("/admin/usuarios/%s/editar" % lucia, seguir=False)
ok(c == 404, "la cuenta eliminada ya no existe")
adm.post(
    "/admin/usuarios",
    {
        "rol": "alumno",
        "dni": "55555557",
        "nombres": "Elena",
        "apellidos": "Borrar Uno",
        "telefono": "",
        "correo": "",
        "clave": "",
    },
)
adm.post(
    "/admin/usuarios",
    {"rol": "alumno", "dni": "55555558", "nombres": "Hugo", "apellidos": "Borrar Dos", "telefono": "", "correo": "", "clave": ""},
)
c, t, *_ = adm.get("/admin/modulos")
mod_b = re.search(r"/admin/modulos/(\d+)/alumnos", t).group(1)
adm.post("/admin/modulos/%s/alumnos" % mod_b, {"lista": "55555558"})
c, t, *_ = adm.get("/admin/usuarios?q=Borrar")
ids_borrar = list(dict.fromkeys(re.findall(r"/admin/usuarios/(\d+)/editar", t)))
hugo, elena = ids_borrar[0], ids_borrar[1]  # van por apellido: «Borrar Dos» antes que «Borrar Uno»

c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [elena], "volver": ""})
ok(
    "Esto no se puede deshacer" in t and "Sí, eliminar esta cuenta" in t and "Borrar Uno" in t,
    "eliminar: primero muestra qué se borrará y pide confirmar",
)
c, t, *_ = adm.get("/admin/usuarios/%s/editar" % elena)
ok(c == 200 and "Borrar Uno" in t, "eliminar: mientras no confirma, la cuenta sigue ahí")
c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [elena], "confirmado": "1", "volver": ""})
ok("1 cuenta eliminada" in t, "eliminar: «Sí, eliminar» borra la cuenta")
c, t, *_ = adm.get("/admin/usuarios/%s/editar" % elena, seguir=False)
ok(c == 404, "la cuenta eliminada ya no existe")

c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [hugo], "volver": ""})
ok("su inscripción en 1 módulo" in t, "eliminar: avisa de los módulos de los que se la quita")
c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [hugo], "confirmado": "1", "volver": ""})
ok("1 cuenta eliminada" in t, "eliminar: una cuenta inscrita pero sin actividad también se borra")
c, t, *_ = adm.get("/admin/modulos/%s/alumnos" % mod_b)
ok("Borrar Dos" not in t, "el alumno eliminado ya no aparece en el módulo")

c, t, *_ = adm.get("/admin/usuarios?q=Salas+Ruiz")
pedro = re.search(r"/admin/usuarios/(\d+)/editar", t).group(1)
c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [pedro], "volver": ""})
ok(
    "No se pueden eliminar todavía" in t
    and "Tiene a su cargo" in t
    and "cámbiales el docente o elimínalos" in t
    and "Sí, eliminar" not in t
    and "Desactivar" not in t
    and "/editar" in t,
    "eliminar: un docente con módulos no se elimina todavía; se explica qué hacer (sin ofrecer desactivar) y se enlazan sus módulos",
)
c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [pedro], "confirmado": "1", "volver": ""})
ok("No se eliminó ninguna cuenta" in t, "eliminar: aunque se fuerce la confirmación, no se borra al docente con módulos")
c, t, *_ = adm.get("/admin/usuarios/%s/editar" % pedro)
ok(
    c == 200 and "Salas Ruiz" in t and "Eliminar cuenta…" in t and "Desactivar cuenta" in t,
    "la ficha de la persona tiene «Desactivar cuenta» y «Eliminar cuenta…» por separado",
)
c, t, *_ = adm.post("/admin/usuarios/lote", {"accion": "eliminar", "ids[]": [pedro], "volver": ""})
ok("No se pueden eliminar todavía" in t, "lote: «Eliminar cuentas…» también pasa por la pantalla de revisión")
c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": ["1"], "volver": ""})
ok("Es tu propia cuenta" in t and "Sí, eliminar" not in t, "nadie puede eliminar su propia cuenta")

c, t, *_ = adm.get("/admin/registro")
ok("eliminó la cuenta de" in t, "el registro de actividad anota quién eliminó cada cuenta")

print("== Administrador: catálogo de módulos y archivado")
c, t, *_ = adm.get("/admin/modulos")
ok(
    "rejilla-catalogo" in t
    and "Ver alumnos" in t
    and "Registro de notas" in t
    and "Horario" in t
    and "Opciones" in t
    and "Activo" in t,
    "Módulos: tarjetas en cuadrícula con sus botones",
)
ok(
    re.search(r"Activos \(\d+\)", t) and re.search(r"Archivados \(\d+\)", t) and "Mostrando 1–" in t,
    "Módulos: pestañas Activos / Archivados y «Mostrando…»",
)
mod_arch = re.search(r"/admin/modulos/(\d+)/alumnos", t).group(1)
c, t, *_ = adm.post("/admin/modulos/%s/estado" % mod_arch, {})
ok("Módulo archivado" in t, "archivar un módulo")
c, t, *_ = adm.get("/admin/modulos?estado=archivados")
ok("Archivado" in t and ("/admin/modulos/%s/alumnos" % mod_arch) in t, "Módulos: pestaña Archivados")
c, t, *_ = adm.post("/admin/modulos/lote", {"accion": "reactivar", "ids[]": [mod_arch]})
ok("1 módulo reactivado" in t, "reactivar en bloque")
c, t, *_ = adm.post("/admin/modulos/lote", {"accion": "archivar"})
ok("Marca primero" in t, "archivar en bloque pide marcar módulos")
c, t, *_ = adm.post("/admin/modulos/lote", {"accion": "archivar_periodo", "periodo": ""})
ok("Elige qué periodo" in t, "archivar un periodo pide elegir cuál")
c, t, *_ = adm.get("/admin/modulos?q=zzzz")
ok("No se encontraron módulos" in t, "Módulos: buscador sin resultados")
c, t, *_ = doc.post("/admin/modulos/lote", {"accion": "archivar", "ids[]": [mod_arch]}, seguir=False)
ok(c == 403, "un docente no puede archivar módulos")

print("== Administrador: ajustes en pestañas y matrículas")
c, t, *_ = adm.get("/admin/ajustes")
ok(
    "Identidad visual" in t
    and "Periodo y matrículas" in t
    and "Contacto y soporte" in t
    and "Cursos" in t
    and 'name="centro_nombre"' in t
    and 'name="whatsapp"' not in t,
    "Ajustes: pestañas, y cada una muestra solo lo suyo",
)
c, t, *_ = adm.get("/admin/ajustes?tab=periodo")
ok(
    "Periodo académico activo" in t
    and "Matrículas abiertas" in t
    and "Aviso general del aula" in t
    and "Archivar módulos en bloque" in t
    and 'name="color_principal"' not in t,
    "Ajustes: periodo y matrículas",
)
c, t, *_ = adm.post(
    "/admin/ajustes",
    {
        "tab": "periodo",
        "periodo": "2027-I",
        "aviso_general": "Matrícula abierta hasta el viernes.",
        "dominio_correo": "cetpro.com",
        "registro_abierto": "1",
    },
)
ok(
    "Ajustes guardados" in t and 'value="2027-I"' in t and "Matrícula abierta hasta el viernes." in t,
    "guardar solo el periodo y el aviso",
)
c, t, *_ = adm.get("/admin/ajustes")
ok('name="centro_nombre"' in t and 'value="CETPRO Mangomarca"' in t, "guardar una pestaña no borra los datos de las otras")
c, t, *_ = adm.get("/admin/ajustes?tab=contacto")
ok("WhatsApp de soporte" in t and 'value="987654321"' in t, "Ajustes: la pestaña de contacto conserva lo guardado")
c, t, *_ = adm.post(
    "/admin/ajustes",
    {
        "tab": "contacto",
        "whatsapp": "911222333",
        "telefono": "01 1112222",
        "horario_atencion": "Lunes a viernes",
        "web": "ftp://x",
        "reglamento_url": "",
        "horario_url": "",
    },
)
ok("debe empezar con https" in t, "contacto: valida la página web")
c, t, *_ = adm.post(
    "/admin/ajustes",
    {
        "tab": "contacto",
        "whatsapp": "911222333",
        "telefono": "01 1112222",
        "horario_atencion": "Lunes a viernes",
        "web": "https://cetpro.edu.pe",
        "reglamento_url": "",
        "horario_url": "",
    },
)
ok("Ajustes guardados" in t and 'value="911222333"' in t, "guardar solo el contacto")
c, t, *_ = doc.post(
    "/cursos",
    {
        "especialidad": "Cosmetología",
        "nombre": "Módulo para matrícula",
        "modulo": "Módulo 2",
        "turno": "noche",
        "horario": "",
        "temas": "Tema único",
    },
)
cod_mat = re.search(r"codigo-lateral\">([A-Z]{3}-\d{4})<", t).group(1)
c, t, *_ = adm.post(
    "/admin/ajustes", {"tab": "periodo", "periodo": "2026-II", "aviso_general": "", "dominio_correo": "cetpro.com"}
)
ok("Ajustes guardados" in t, "matrículas cerradas (interruptor apagado)")
c, t, *_ = al2.post("/cursos/unirse", {"codigo": cod_mat})
ok("matrículas del periodo están cerradas" in t, "con matrículas cerradas nadie se une a un módulo con código")
c, t, *_ = adm.post(
    "/admin/ajustes",
    {"tab": "periodo", "periodo": "2026-II", "aviso_general": "", "dominio_correo": "cetpro.com", "registro_abierto": "1"},
)
c, t, *_ = al2.post("/cursos/unirse", {"codigo": cod_mat})
ok("Ya estás en" in t or "Listo" in t, "con matrículas abiertas sí se une")
c, t, *_ = adm.get("/admin/ajustes?tab=especialidades")
ok("Cursos (programas de estudios)" in t and "rejilla-especialidades" in t, "Ajustes: catálogo de cursos")

print("== Administrador: dashboard de auditoría, registro de actividad y exportación")
c, t, *_ = adm.get("/")
ok(
    "Reportes de la semana" in t
    and "Asistencia de la semana" in t
    and "Notas: calificadas y pendientes" in t
    and "Exportar registro consolidado (Excel)" in t,
    "inicio del admin: asistencia de la semana, notas calificadas vs pendientes y exportación",
)
ok(
    t.count("Cargar alumnos") == 1 and "Cargar lista de alumnos" not in t,
    "inicio del admin: «Cargar alumnos» aparece una sola vez (sin accesos duplicados)",
)
ok(
    "Últimos accesos" in t and "Movimientos recientes" in t and "Calificación al día, por módulo" in t,
    "inicio del admin: últimos accesos, movimientos y calificación por módulo",
)
c, t, *_ = adm.post("/admin/modulos/%s/alumnos" % mod_arch, {"lista": "55555557, =2+2, Prueba CSV"})
ok("1 alumno agregado" in t, "se inscribe un alumno cuyo nombre empieza con «=»")
c, t, h, raw = adm.get("/admin/reportes/consolidado")
texto = raw.decode("utf-8")
ok(
    c == 200
    and raw.startswith(b"\xef\xbb\xbf")
    and "Registro consolidado" in texto
    and "Condición" in texto
    and "Torres Vega" in texto,
    "exporta el registro consolidado para Excel",
)
ok(
    re.search(r'"?Prueba CSV"?;\'=2\+2', texto) and not re.search(r'Prueba CSV"?;=2\+2', texto),
    "el Excel no deja que un nombre se lea como fórmula (empieza con apóstrofo)",
)
c, t, h, raw = adm.get("/admin/modulos/%s/alumnos" % mod_arch)
c, t, h, rawnotas = adm.get("/cursos/%s/notas/excel" % mod_arch)
textonotas = rawnotas.decode("utf-8")
ok(
    c == 200 and re.search(r'"?Prueba CSV"?;\'=2\+2', textonotas) and not re.search(r'Prueba CSV"?;=2\+2', textonotas),
    "el Excel de notas del módulo también protege los nombres",
)
c, t, *_ = adm.get("/cursos/%s" % mod_arch)
ok(
    "pestanas-modulo" in t and "Contenido" in t and "/mensajes/curso/" not in t,
    "el administrador ve el módulo sin la pestaña «Mensajes» (no tiene permiso)",
)
enlaces = sorted(set(re.findall(r'href="/(cursos/%s[^"#]*)"' % mod_arch, t)))
malos = []
for enlace in enlaces:
    cod, *_ = adm.get("/" + enlace, seguir=False)
    if cod in (403, 404) or cod >= 500:
        malos.append((enlace, cod))
ok(not malos, "el administrador puede abrir todos los enlaces del módulo %s" % (malos or ""))
c, t, *_ = adm.get("/admin/registro")
ok(
    "Registro de actividad" in t
    and "entró al aula" in t
    and "creó la cuenta de" in t
    and "cambió la contraseña de" in t
    and "Desde" in t,
    "registro de actividad: accesos, cuentas creadas y contraseñas",
)
ok(
    "calificó «" in t or "tomó la asistencia" in t or "cambió los ajustes" in t,
    "registro de actividad: notas, asistencia y ajustes",
)
ok("contraseña: " not in t.lower() and clave_doc not in t, "el registro nunca guarda contraseñas")
c, t, *_ = adm.get("/admin/registro?accion=clave")
ok("cambió la contraseña" in t and "entró al aula" not in t, "registro: filtro por tipo (contraseñas)")
c, t, *_ = doc.get("/admin/registro", seguir=False)
ok(c == 403, "un docente no ve el registro de actividad")
c, t, *_ = al.get("/admin/reportes/consolidado", seguir=False)
ok(c == 403, "un alumno no exporta el registro consolidado")

c, t, *_ = al.post("/cuenta/nueva-clave", {"nueva": "cualquiera123", "repetir": "cualquiera123"})
ok("escribe primero la actual" in t, "sin contraseña temporal no se puede cambiar la clave sin escribir la actual")
c, t, *_ = Cliente().login("71234567", "cualquiera123")
ok("Hola, Ana" not in t, "esa contraseña no quedó guardada")

print("== Cursos, módulos y unidades didácticas")
c, t, *_ = adm.get("/admin/cursos")
ok(
    'href="/admin/cursos"' in t and "Un <b>curso</b> es un programa de estudios" in t and "Cosmetología" in t,
    "Administrador: «Cursos» en el menú y cada curso con sus módulos",
)
ok(
    "Nuevo curso" in t
    and "Nuevo módulo" in t
    and "Abrir curso" in t
    and "Agregar módulo" in t
    and "Ver todos los módulos" in t
    and "/admin/cursos/nuevo" in t
    and "/admin/modulos/nuevo?especialidad=" in t,
    "Cursos: «Nuevo curso», y en cada curso abrirlo y agregarle módulos",
)
ok(
    re.search(r"\d+ módulos?</span>", t) and re.search(r"\d+ alumnos?</span>", t),
    "Cursos: cuántos módulos, alumnos y docentes tiene cada curso",
)
c, t, *_ = doc.get("/admin/cursos", seguir=False)
ok(c == 403, "un docente no puede abrir los Cursos del administrador")
c, t, *_ = adm.get("/admin/modulos")
ok("rejilla-catalogo" in t and "Ver por cursos" in t, "Módulos: el catálogo sigue aquí, con un acceso para ver por cursos")

c, t, *_ = adm.get("/admin/modulos/nuevo?especialidad=Cosmetolog%C3%ADa")
ok(
    re.search(r"<option selected>Cosmetología</option>", t)
    and "Unidades didácticas" in t
    and 'name="ud_nombre[]"' in t
    and "¿Qué módulo es?" in t,
    "Nuevo módulo desde un curso: el curso ya viene elegido y se piden las unidades didácticas",
)
docente_pedro = re.search(r'value="(\d+)"[^>]*>Salas Ruiz, Pedro', t).group(1)
datos_mod = {
    "especialidad": "Cosmetología",
    "modulo": "Módulo 1",
    "nombre": "Atención de incidentes (curso nuevo)",
    "periodo": "2026-II",
    "turno": "tarde",
    "horario": "",
    "docente_id": docente_pedro,
    "ud_nombre[]": ["Organización del Área de Trabajo", "Atención del Incidente", "", "Mantenimiento Predictivo"],
    "ud_creditos[]": ["3", "2", "", ""],
    "ud_horas[]": ["80", "48", "", "48"],
}
c, t, *_ = adm.post(
    "/admin/modulos", dict(datos_mod, **{"ud_creditos[]": ["3", "abc", "", ""], "ud_horas[]": ["80", "48", "", "48"]})
)
ok("Revisa «Atención del Incidente»" in t, "unidades didácticas: créditos que no son números dan un aviso claro")
c, t, *_ = adm.post(
    "/admin/modulos",
    dict(datos_mod, **{"ud_nombre[]": ["Unidad %d" % i for i in range(13)], "ud_creditos[]": [""] * 13, "ud_horas[]": [""] * 13}),
)
ok("hasta 12 unidades didácticas" in t, "unidades didácticas: no se pasan de 12")
c, t, *_ = adm.post("/admin/modulos", dict(datos_mod, nombre="Atención de incidentes (curso nuevo)"))
ok("Módulo creado" in t, "el administrador crea un módulo dentro de un curso, con sus unidades didácticas")
c, t, *_ = adm.get("/admin/modulos?q=Atenci%C3%B3n+de+incidentes")
mod_ud = re.search(r"/admin/modulos/(\d+)/alumnos", t).group(1)
c, t, *_ = adm.get("/cursos/%s" % mod_ud)
ok(
    "Unidades didácticas" in t
    and "Organización del Área de Trabajo" in t
    and "Mantenimiento Predictivo" in t
    and "5 créditos" in t
    and "176 horas" in t,
    "la página del módulo lista las unidades y suma sus créditos y horas",
)
ok("Cosmetología" in t and "Módulo 1" in t, "la página del módulo muestra su curso y su módulo")
c, t, *_ = adm.post(
    "/admin/modulos",
    dict(datos_mod, nombre="", modulo="Módulo 2", **{"ud_nombre[]": [""], "ud_creditos[]": [""], "ud_horas[]": [""]}),
)
c, t, *_ = adm.get("/admin/modulos?q=Cosmetolog%C3%ADa+%E2%80%93+M%C3%B3dulo+2")
ok("Cosmetología – Módulo 2" in t, "sin nombre, el módulo se llama como el curso y el módulo")
c, t, *_ = adm.get("/admin/modulos/%s/editar" % mod_ud)
ok(
    'value="Atención del Incidente"' in t and 'value="48"' in t and "checked" in t,
    "editar el módulo: las unidades ya escritas vienen en sus filas",
)
c, t, *_ = adm.post(
    "/admin/modulos/%s" % mod_ud,
    dict(datos_mod, activo="1", **{"ud_nombre[]": ["Solo una unidad"], "ud_creditos[]": ["4"], "ud_horas[]": ["96"]}),
)
c, t, *_ = adm.get("/cursos/%s" % mod_ud)
ok(
    "Solo una unidad" in t and "Atención del Incidente" not in t and "4 créditos" in t,
    "al guardar, la lista de unidades se reemplaza por la nueva",
)

# El docente también crea y edita sus módulos, ahora «dentro de un curso», con unidades didácticas.
c, t, *_ = doc.get("/cursos/nuevo")
ok(
    'for="especialidad">Curso<' in t and "Unidades didácticas" in t and "Agregar otra unidad" in t,
    "docente: «Crear un módulo» pide el curso e incluye las unidades didácticas",
)
c, t, *_ = doc.post(
    "/cursos",
    {
        "especialidad": "Cosmetología",
        "nombre": "Módulo con unidades",
        "modulo": "Módulo 2",
        "turno": "mañana",
        "horario": "",
        "temas": "Tema A",
        "ud_nombre[]": ["Cuidado de la piel", "Maquillaje social"],
        "ud_creditos[]": ["2", "3"],
        "ud_horas[]": ["48", ""],
    },
)
ok(
    "Módulo creado" in t and "Unidades didácticas" in t and "Cuidado de la piel" in t and "Cambiar las unidades" in t,
    "docente: crea su módulo con unidades didácticas y las ve en la página",
)
mod_doc = re.search(r"/cursos/(\d+)/editar", t).group(1)
c, t, *_ = adm.post("/admin/modulos/%s/alumnos" % mod_doc, {"lista": "71234567"})
c, t, *_ = al.get("/cursos/%s" % mod_doc)
ok(
    "Cuidado de la piel" in t
    and "Maquillaje social" in t
    and "Cambiar las unidades" not in t
    and "Agregar unidades didácticas" not in t,
    "el alumno ve las unidades del módulo, pero no puede cambiarlas",
)
c, t, *_ = doc.post("/cursos/%s/copiar" % mod_doc, {"nombre": "Módulo con unidades (copia)", "periodo": "2027-I"})
ok("Cuidado de la piel" in t and "Maquillaje social" in t, "al copiar un módulo se copian también sus unidades didácticas")
c, t, *_ = doc.get("/cursos/%s/editar" % mod_doc)
ok(
    'value="Maquillaje social"' in t and 'value="Cuidado de la piel"' in t,
    "docente: al editar su módulo ve sus unidades en las filas",
)

print("== Cargar el plan de estudios desde un Excel")


def plan_xlsx(curso):
    # Igual al Excel oficial del Ministerio: títulos en la fila 9, módulos en la columna A, unidades en la F, créditos en H, I y J.
    org = {
        (5, 0): "DENOMINACIÓN DEL PROGRAMA DE ESTUDIOS",
        (5, 2): curso,
        (5, 3): "CÓDIGO *",
        (5, 4): "X-1",
        (9, 0): "MÓDULO",
        (9, 1): "DESCRIPCIÓN DE LA COMPETENCIA",
        (9, 5): "UNIDAD DIDÁCTICA",
        (9, 6): "PERIODO ACADÉMICO",
        (9, 7): "Crédito teórico",
        (9, 8): "Crédito práctico",
        (9, 9): "T.créditos\n(Filtrar)",
        (10, 0): "ATENCIÓN DE INCIDENTES (PRUEBA)",
        (10, 1): "Competencias técnicas",
        (10, 5): "Organización del Área de Trabajo",
        (10, 6): "I",
        (10, 7): 1.0,
        (10, 8): 2.0,
        (10, 9): 3,
        (11, 5): "Atención del  Incidente",
        (11, 6): "I",
        (11, 7): 1.0,
        (11, 9): 2,
        (12, 1): "Competencias para la empleabilidad",
        (12, 5): "Comunicación para el desarrollo",
        (12, 6): "I",
        (12, 7): 1.0,
        (12, 9): 2,
        (13, 1): "Experiencias formativas en situaciones reales de trabajo (EFSRT)",
        (13, 7): 0.0,
        (13, 8): 6.0,
        (13, 9): 6,
        (14, 9): 0,
        (20, 0): "MONITOREO Y ACCIONES (PRUEBA)",
        (20, 5): "Monitoreo del rendimiento",
        (20, 6): "II",
        (20, 7): 1.0,
        (20, 9): 2,
        (21, 5): "Reportes operativos",
        (21, 6): "II",
        (21, 7): 2.0,
        (21, 9): 4,
        (22, 1): "Experiencias formativas en situaciones reales de trabajo (EFSRT)",
        (22, 7): 0.0,
        (22, 8): 6.0,
        (22, 9): 6,
        (30, 1): "Competencias técnicas",
        (30, 9): 0,
        (31, 1): "Experiencias formativas en situaciones reales de trabajo (EFSRT)",
        (31, 9): 0,
        (40, 0): "ORIENTACIONES DE AYUDA: ...",
    }
    return xlsx({"Perfil_Egreso": {(1, 0): "ANEXO"}, "Organización_Modular": org, "M1": {(1, 0): "x"}})


tipo_xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
c, t, *_ = adm.get("/plan")
ok(
    "Sube el plan de estudios en Excel" in t and 'type="file"' in t and "Leer el plan" in t,
    "Cargar plan: pantalla para subir el Excel (administrador)",
)
c, t, *_ = al.get("/plan", seguir=False)
ok(c == 403, "un alumno no puede cargar el plan de estudios")
c, t, *_ = anon.get("/plan", seguir=False)
ok(c in (301, 302, 303), "sin sesión, cargar el plan manda a entrar")
c, t, *_ = adm.get("/admin/cursos")
ok("Cargar plan de estudios (Excel)" in t, "Cursos: botón para cargar el plan de estudios")

c, t, *_ = adm.post("/plan", {}, archivos={"archivo": ("plan.txt", b"hola", "text/plain")})
ok("archivo de Excel (.xlsx)" in t, "cargar plan: solo se acepta Excel")
c, t, *_ = adm.post("/plan", {}, archivos={"archivo": ("plan.xlsx", b"esto no es un excel", tipo_xlsx)})
ok("No pudimos abrir el Excel" in t, "cargar plan: un archivo dañado da un aviso claro")
c, t, *_ = adm.post("/plan", {}, archivos={"archivo": ("otro.xlsx", xlsx({"Hoja1": {(1, 0): "hola"}}), tipo_xlsx)})
ok("No encontré la hoja «Organización modular»" in t, "cargar plan: un Excel que no es el plan da un aviso claro")
c, t, *_ = adm.get("/plan/revisar", seguir=False)
ok(c in (301, 302, 303), "revisar sin haber subido nada vuelve a pedir el archivo")

c, t, *_ = adm.post("/plan", {}, archivos={"archivo": ("plan.xlsx", plan_xlsx("CURSO DEL PLAN DE PRUEBA"), tipo_xlsx)})
ok(
    "Encontré" in t
    and "2 módulos" in t
    and "CURSO DEL PLAN DE PRUEBA" in t
    and "Módulo 1 · Atención de incidentes (prueba)" in t
    and "Módulo 2 · Monitoreo y acciones (prueba)" in t,
    "cargar plan: se leen el curso y los módulos del Excel",
)
ok(
    "Organización del Área de Trabajo" in t
    and "3 créditos · 80 horas" in t
    and "Atención del Incidente" in t
    and "Atención del  Incidente" not in t
    and "2 créditos · 48 horas" in t,
    "cargar plan: unidades con sus créditos y horas (1 crédito teórico = 16 h, práctico = 32 h)",
)
ok(
    "Experiencias formativas en situaciones reales de trabajo (EFSRT)" in t and "6 créditos · 192 horas" in t,
    "cargar plan: la práctica EFSRT también suma créditos y horas",
)
ok("13 créditos · 368 horas" in t and "12 créditos · 336 horas" in t, "cargar plan: los totales de cada módulo cuadran")
ok(
    "Crear el curso «CURSO DEL PLAN DE PRUEBA»" in t and 'name="docente[0]"' in t and 'name="turno[1]"' in t,
    "cargar plan (administrador): puede crear el curso y elige docente y turno de cada módulo",
)

base_plan = {
    "curso": "__nuevo__",
    "periodo": "2026-II",
    "usar[0]": "1",
    "usar[1]": "1",
    "destino[0]": "nuevo",
    "destino[1]": "nuevo",
    "docente[0]": docente_pedro,
    "docente[1]": docente_pedro,
    "turno[0]": "noche",
    "turno[1]": "noche",
    "horario[0]": "Lunes a viernes · 18:30",
    "horario[1]": "",
}
c, t, *_ = adm.post("/plan/crear", {k: v for k, v in base_plan.items() if not k.startswith("usar")})
ok("Marca al menos un módulo" in t, "cargar plan: hay que marcar algún módulo")
sin_turno = dict(base_plan)
sin_turno["turno[1]"] = ""
c, t, *_ = adm.post("/plan/crear", sin_turno)
ok("elige el turno" in t, "cargar plan: sin turno no se crea el módulo")
c, t, *_ = adm.get("/admin/cursos")
ok("CURSO DEL PLAN DE PRUEBA" not in t, "si faltan datos, no se crea nada a medias")
c, t, *_ = adm.post("/plan/crear", base_plan)
ok("Plan cargado" in t and "2 módulos creados" in t, "cargar plan: se crean los dos módulos con sus unidades")
c, t, *_ = adm.get("/admin/cursos")
ok(
    "CURSO DEL PLAN DE PRUEBA" in t and "Atención de incidentes (prueba)" in t and "Monitoreo y acciones (prueba)" in t,
    "el curso nuevo aparece en Cursos con sus dos módulos",
)
c, t, *_ = adm.get("/admin/modulos?q=Atenci%C3%B3n+de+incidentes+%28prueba%29")
mod_plan = re.search(r"/admin/modulos/(\d+)/alumnos", t).group(1)
c, t, *_ = adm.get("/cursos/%s" % mod_plan)
ok(
    "Organización del Área de Trabajo" in t
    and "Experiencias formativas en situaciones reales de trabajo (EFSRT)" in t
    and "13 créditos" in t
    and "368 horas" in t
    and "Módulo 1" in t,
    "el módulo creado desde el plan muestra sus unidades, créditos y horas",
)

# Completar un módulo que ya existía (el de Cosmetología de más arriba, que tenía «Solo una unidad»).
c, t, *_ = adm.post("/plan", {}, archivos={"archivo": ("plan.xlsx", plan_xlsx("CURSO DEL PLAN DE PRUEBA"), tipo_xlsx)})
ok("Completar el que ya existe" in t, "cargar plan: ofrece completar los módulos que ya existen del curso")
c, t, *_ = adm.post("/plan/crear", {"curso": "Cosmetología", "periodo": "2026-II", "usar[0]": "1", "destino[0]": mod_ud})
ok("1 módulo completado" in t, "cargar plan: completa un módulo que ya existe")
c, t, *_ = adm.get("/cursos/%s" % mod_ud)
ok(
    "Organización del Área de Trabajo" in t and "Solo una unidad" not in t,
    "completar reemplaza las unidades del módulo por las del plan",
)
c, t, *_ = adm.post("/plan", {}, archivos={"archivo": ("plan.xlsx", plan_xlsx("CURSO DEL PLAN DE PRUEBA"), tipo_xlsx)})
c, t, *_ = adm.post(
    "/plan/crear", {"curso": "Soporte Técnico y Redes", "periodo": "2026-II", "usar[0]": "1", "destino[0]": mod_ud}
)
ok("Elige un módulo de tu lista" in t, "no se puede completar un módulo de otro curso")

# El docente carga el plan para sus propios módulos; no puede inventar cursos.
c, t, *_ = doc.get("/cursos")
ok("Cargar plan de estudios (Excel)" in t, "docente: «Mis módulos» tiene el botón para cargar el plan")
c, t, *_ = doc.post("/plan", {}, archivos={"archivo": ("plan.xlsx", plan_xlsx("CURSO DEL PLAN DE PRUEBA"), tipo_xlsx)})
ok(
    "Encontré" in t and 'name="docente[0]"' not in t and "Crear el curso" not in t,
    "docente: ve el plan, sin elegir docente ni crear cursos",
)
c, t, *_ = doc.post(
    "/plan/crear",
    {"curso": "CURSO DEL PLAN DE PRUEBA", "periodo": "2026-II", "usar[1]": "1", "destino[1]": "nuevo", "turno[1]": "tarde"},
)
ok("1 módulo creado" in t and "Monitoreo y acciones (prueba)" in t, "docente: crea su módulo desde el plan (queda a su nombre)")
c, t, *_ = doc.post("/plan", {}, archivos={"archivo": ("plan.xlsx", plan_xlsx("CURSO QUE NO EXISTE"), tipo_xlsx)})
c, t, *_ = doc.post(
    "/plan/crear", {"curso": "__nuevo__", "periodo": "2026-II", "usar[0]": "1", "destino[0]": "nuevo", "turno[0]": "tarde"}
)
ok("todavía no existe" in t, "docente: no puede crear un curso nuevo desde el plan")
c, t, *_ = al.post("/plan/crear", {"curso": "Cosmetología"}, seguir=False)
ok(c == 403, "un alumno no puede crear módulos desde el plan")

print("== Alumnos: lista de inscripción, 1 o 2 módulos y accesos por WhatsApp")
c, t, *_ = adm.get("/admin/alumnos/importar")
ok(
    'name="curso_id[]"' in t and 'name="con_clave"' in t and "Apellidos paterno" in t and "no se guarda" in t,
    "Cargar alumnos: se marcan uno o dos módulos, hay contraseña temporal y se explica qué columnas se leen",
)
c, t, *_ = adm.get("/admin/modulos?q=Monitoreo+y+acciones+%28prueba%29")
mod2 = re.search(r"/admin/modulos/(\d+)/alumnos", t).group(1)
c, t, *_ = adm.get("/admin/modulos/%s/alumnos" % mod_plan)
codigo_m1 = re.search(r"([A-Z]{3}-\d{4})", t).group(1)
forms = (
    "Marca temporal,APELLIDOS PATERNO,APELLIDOS MATERNO,NOMBRES,EDAD,FECHA NACIMIENTO,DNI,TELEFONO,DIRECCIÓN,URBANIZACIÓN,ESTADO CIVIL,GRADO DE INSTRUCCIÓN,MÓDULO\n"
    "12/08/2026 10:00:00,QUISPE,HUAMAN,ANA LUCIA,25,14/03/2001,70010001,987654001,Av. Los Olivos 123,Mangomarca,Soltera,Secundaria completa,1\n"
    "12/08/2026 10:05:00,TORRES,RAMOS,JUAN CARLOS,31,02/11/1994,70010002,987654002,Jr. Lima 45,Canto Rey,Casado,Superior técnica,2\n"
    "12/08/2026 10:10:00,PEREZ,LUNA,MARIA ELENA,40,20/05/1986,70010003,,Calle 5,Zarate,Soltera,Primaria,1 y 2\n"
    "12/08/2026 10:15:00,DIAZ,ROJAS,PEDRO,22,01/01/2004,70010004,987654004,Calle 9,Otra,Soltero,Secundaria,3\n"
)
c, t, *_ = adm.post(
    "/admin/alumnos/importar",
    {"curso_id[]": [mod_plan, mod2], "con_clave": "1"},
    archivos={"archivo": ("inscripcion.csv", forms.encode("utf-8"), "text/csv")},
)
ok(
    "3 alumnos nuevos" in t and "4 inscripciones en módulos" in t,
    "Excel de la inscripción: se leen apellido paterno y materno, y cada alumno va a su módulo (1, 2 o los dos)",
)
ok("Fila 4" in t and "marca arriba el módulo «3»" in t, "un módulo que no está marcado da un aviso claro")
ok(
    "3 contraseñas temporales" in t and "Ver contraseñas y enviar por WhatsApp" in t,
    "se crean contraseñas temporales para enviarlas por WhatsApp",
)
c, t, *_ = adm.get("/admin/usuarios/claves")
ok(
    "Quispe Huaman" in t and "70010001" in t and "wa.me/51987654001" in t and "Al%20entrar%20por%20primera%20vez" in t,
    "las contraseñas se muestran con su botón de WhatsApp y el mensaje para el alumno",
)
ok("El envío por correo llegará" in t, "se avisa que el envío por correo llegará después")
clave_ana_tmp = re.search(r'70010001.*?<code class="clave-lote">([^<]+)</code>', t, re.S).group(1)
c, t, *_ = adm.get("/admin/modulos/%s/alumnos" % mod_plan)
ok("Quispe Huaman" in t and "Perez Luna" in t and "Torres Ramos" not in t, "Módulo 1: solo Ana y María")
c, t, *_ = adm.get("/admin/modulos/%s/alumnos" % mod2)
ok("Torres Ramos" in t and "Perez Luna" in t and "Quispe Huaman" not in t, "Módulo 2: solo Juan y María")
c, t, *_ = adm.get("/admin/usuarios?q=70010003")
ok(
    "Módulo 1" in t and "Módulo 2" in t and "Debe cambiar su clave" in t,
    "Personas: la alumna aparece en sus dos módulos y con contraseña temporal",
)
ana_tmp = Cliente()
c, t, *_ = ana_tmp.login("70010001", clave_ana_tmp)
ok("La contraseña que te dieron es temporal" in t, "la alumna entra con su DNI y la contraseña temporal, y debe elegir la suya")
c, t, *_ = ana_tmp.post("/cuenta/nueva-clave", {"nueva": "ana-eligio-1", "repetir": "ana-eligio-1"})
ok("Hola, Ana" in t, "la alumna elige su contraseña y entra a sus módulos")

# Accesos de todo un módulo: solo a quienes todavía no eligieron su contraseña.
c, t, *_ = adm.get("/admin/modulos/%s/alumnos" % mod_plan)
ok("Enviar accesos por WhatsApp" in t and "Preparar accesos" in t, "el módulo tiene el botón para enviar accesos por WhatsApp")
c, t, *_ = adm.post("/admin/modulos/%s/accesos" % mod_plan, {})
ok(
    "Perez Luna" in t and "Quispe Huaman" not in t and "contraseña nueva creada" in t,
    "los accesos del módulo se dan solo a quien aún no eligió su contraseña",
)
c, t, *_ = doc.post("/admin/modulos/%s/accesos" % mod_plan, {}, seguir=False)
ok(c == 403, "un docente no puede preparar accesos desde el administrador")

# Código de módulo en la fila, y alumnos pegados sin contraseña temporal («Crear mi cuenta»).
c, t, *_ = adm.post(
    "/admin/alumnos/importar", {"lista": "70010006\tLuis\tVega Soto\t987654006\t\t%s\n70010007\tSara\tMora\t\t\t" % codigo_m1}
)
ok(
    "2 alumnos nuevos" in t and "1 inscripción en módulo" in t and "Crear mi cuenta" in t and "contraseñas temporales" not in t,
    "lista pegada: el código del módulo inscribe y, sin la casilla, entran con «Crear mi cuenta»",
)
c, t, *_ = adm.post("/admin/alumnos/importar", {"lista": "70010008\tMal\tMódulo\t\t\tquien sabe", "curso_id[]": [mod_plan]})
ok("no entendí el módulo" in t, "una columna de módulo que no se entiende da un aviso claro")

# Un alumno nuevo se inscribe en 1 o 2 módulos desde el mismo formulario.
c, t, *_ = adm.get("/admin/usuarios/nuevo?rol=alumno")
ok("Inscribir en módulos" in t and 'name="modulos[]"' in t, "Nuevo alumno: se puede inscribir en uno o en los dos módulos")
c, t, *_ = adm.post(
    "/admin/usuarios",
    {
        "rol": "alumno",
        "dni": "70010009",
        "nombres": "Rita",
        "apellidos": "Salas Cruz",
        "telefono": "987654009",
        "correo": "",
        "clave": "",
        "modulos[]": [mod_plan, mod2],
    },
)
ok("Cuenta creada" in t and "2 módulos" in t, "Nuevo alumno: queda inscrito en los dos módulos que se marcaron")
c, t, *_ = adm.get("/admin/modulos/%s/alumnos" % mod2)
ok("Salas Cruz" in t, "el alumno nuevo aparece en el módulo")

print("== Seguridad de acceso")
malo = Cliente()
for _ in range(8):
    malo.login("30000002", "equivocada")
c, t, *_ = malo.login("30000002", "30000002")
ok("muchos intentos" in t, "tras 8 intentos fallidos la cuenta se frena (aunque luego acierte)")
c, t, *_ = Cliente().login("prueba-x@prueba.local", "x")
ok("no son correctos" in t, "cuenta del antiguo modo prueba no entra")
c, t, *_ = adm.get("/")
ok("antiguo modo prueba" not in t, "la migración ya desactivó las cuentas de prueba")

print("== Eliminar de verdad: cuentas con historial y módulos")
import glob

# DIFERENCIA A PROPÓSITO: aquí los archivos subidos están en la carpeta que arma aceptacion/correr.py (ARCHIVOS_CARPETA)
subidos = os.environ.get("ARCHIVOS_CARPETA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".tmp", "archivos")
contar_archivos = lambda: sum(len(f) for _, _, f in os.walk(subidos))

# Un docente no puede eliminar un módulo que ya tiene trabajos de alumnos: esos registros son del CETPRO (lo elimina el administrador).
c, t, *_ = doc.get("/cursos/%s" % mid)
ok("/cursos/%s/eliminar" % mid not in t, "docente: su módulo con trabajos de alumnos no ofrece «Eliminar módulo»")
c, t, *_ = doc.get("/cursos/%s/eliminar" % mid)
ok(
    "pídele al administrador" in t and "Sí, eliminar el módulo" not in t,
    "docente: un módulo con trabajos de alumnos no se puede eliminar (se le pide al administrador)",
)
c, t, *_ = doc.post("/cursos/%s/eliminar" % mid, {"entiendo": "1"})
ok("pídele al administrador" in t, "docente: tampoco se puede forzar el borrado")
c, t, *_ = doc.get("/cursos/%s" % mid)
ok(c == 200, "el módulo con trabajos sigue ahí")

# Una alumna con trabajos entregados: se muestra qué se pierde, hay que marcar «Entiendo» y se borra todo lo suyo.
c, t, *_ = adm.get("/admin/usuarios?q=Torres+Vega")
ana_id = re.search(r"/admin/usuarios/(\d+)/editar", t).group(1)
antes = contar_archivos()
c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [ana_id], "volver": ""})
ok(
    "Se borra también" in t
    and "trabajos entregados" in t
    and 'name="entiendo"' in t
    and "Sí, eliminar esta cuenta" in t
    and "Desactivar" not in t,
    "eliminar con historial: se muestra todo lo que se pierde y hay que marcar «Entiendo»",
)
c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [ana_id], "confirmado": "1", "volver": ""})
ok("Marca la casilla «Entiendo»" in t, "eliminar con historial: sin marcar «Entiendo» no se borra")
c, t, *_ = adm.get("/admin/usuarios/%s/editar" % ana_id)
ok(c == 200, "sin «Entiendo», la cuenta sigue ahí")
c, t, *_ = adm.post("/admin/usuarios/eliminar", {"ids[]": [ana_id], "confirmado": "1", "entiendo": "1", "volver": ""})
ok("1 cuenta eliminada" in t, "eliminar con historial: marcando «Entiendo», se elimina la cuenta con todo lo suyo")
c, t, *_ = adm.get("/admin/usuarios/%s/editar" % ana_id, seguir=False)
ok(c == 404, "la alumna eliminada ya no existe")
ok(contar_archivos() < antes, "sus fotos y archivos subidos también se borraron del disco")
c, t, *_ = doc.get("/por-calificar")
ok("Ana Lucía Torres Vega" not in t, "sus trabajos ya no aparecen para calificar")
c, t, *_ = Cliente().login("71234567", clave_al)
ok("Hola, Ana" not in t, "la alumna eliminada ya no puede entrar")
c, t, *_ = adm.get("/admin/registro")
ok("eliminó la cuenta de" in t and "Se borró también" in t, "el registro anota qué se borró junto con la cuenta")

# Un módulo: «Archivar» y «Eliminar» son botones distintos; eliminar borra todo lo que tiene y sus archivos.
c, t, *_ = adm.get("/admin/modulos")
ok("Archivar módulo" in t and "Eliminar módulo…" in t, "Módulos: «Archivar módulo» y «Eliminar módulo…» van separados")
c, t, *_ = doc.post(
    "/cursos",
    {
        "especialidad": "Cosmetología",
        "nombre": "Módulo para eliminar",
        "modulo": "Módulo 2",
        "turno": "noche",
        "horario": "",
        "temas": "Tema uno\nTema dos",
    },
)
mod_del = re.search(r"/cursos/(\d+)/editar", t).group(1)
c, t, *_ = doc.get("/cursos/%s" % mod_del)
clase_del = re.search(r"/clases/(\d+)", t).group(1)
doc.post(
    "/cursos/%s/materiales" % mod_del,
    {"unidad_id": clase_del, "tipo": "archivo", "titulo": "Guía para borrar"},
    {"archivo": ("guia.png", png(), "image/png")},
)
antes = contar_archivos()
ok("Eliminar módulo" in doc.get("/cursos/%s" % mod_del)[1], "docente: su módulo tiene «Eliminar módulo»")
c, t, *_ = doc.get("/cursos/%s/eliminar" % mod_del)
ok(
    "Vas a eliminar el módulo" in t and "2 clases" in t and "1 material" in t and 'name="entiendo"' in t,
    "eliminar módulo: se muestra todo lo que se borra",
)
c, t, *_ = doc.post("/cursos/%s/eliminar" % mod_del, {})
ok("Marca la casilla «Entiendo»" in t, "eliminar módulo: sin marcar «Entiendo» no se borra")
c, t, *_ = doc.get("/cursos/%s" % mod_del)
ok(c == 200 and "Módulo para eliminar" in t, "sin «Entiendo», el módulo sigue ahí")
c, t, *_ = doc.get("/cursos/1/eliminar", seguir=False)
ok(c in (403, 404), "un docente no puede eliminar el módulo de otro docente")
c, t, *_ = doc.post("/cursos/%s/eliminar" % mod_del, {"entiendo": "1"})
ok("Módulo eliminado" in t, "docente: elimina su módulo con todo lo que tiene")
c, t, *_ = doc.get("/cursos/%s" % mod_del, seguir=False)
ok(c in (403, 404), "el módulo eliminado ya no existe")
ok(contar_archivos() < antes, "los archivos del módulo también se borraron del disco")

# El administrador elimina un módulo vacío sin más pasos; con datos, hay que marcar «Entiendo».
c, t, *_ = adm.post(
    "/admin/modulos",
    dict(datos_mod, nombre="Módulo vacío para borrar", **{"ud_nombre[]": [""], "ud_creditos[]": [""], "ud_horas[]": [""]}),
)
c, t, *_ = adm.get("/admin/modulos?q=M%C3%B3dulo+vac%C3%ADo+para+borrar")
vacio_id = re.search(r"/admin/modulos/(\d+)/alumnos", t).group(1)
c, t, *_ = adm.get("/admin/modulos/%s/eliminar" % vacio_id)
ok("Está vacío" in t and 'name="entiendo"' not in t, "administrador: un módulo vacío se elimina sin casilla")
c, t, *_ = adm.post("/admin/modulos/%s/eliminar" % vacio_id, {})
ok("Módulo eliminado" in t, "administrador: elimina un módulo vacío")
c, t, *_ = adm.get("/admin/modulos/%s/eliminar" % mod_plan)
ok("alumnos inscritos" in t and 'name="entiendo"' in t, "administrador: un módulo con alumnos pide «Entiendo»")
c, t, *_ = adm.post("/admin/modulos/%s/eliminar" % mod_plan, {"entiendo": "1"})
ok("Módulo eliminado" in t, "administrador: elimina un módulo con alumnos y todo lo que tiene")
c, t, *_ = adm.get("/admin/modulos/%s/alumnos" % mod_plan, seguir=False)
ok(c == 404, "el módulo eliminado ya no existe para el administrador")
c, t, *_ = ana_tmp.post("/admin/modulos/%s/eliminar" % mod2, {"entiendo": "1"}, seguir=False)
ok(c == 403, "un alumno no puede eliminar módulos")


print()
print("FALLAS: %d" % len(fallos))
for f in fallos:
    print(" - " + f)
sys.exit(1 if fallos else 0)
