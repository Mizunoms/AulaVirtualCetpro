"""Funciones comunes: dirección del visitante, mensajes, fechas en español y enlaces de WhatsApp."""

import re
from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render
from django.urls import get_script_prefix
from django.utils import timezone

DIAS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"]
MESES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip
MESES_CORTO = ["", "ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SET", "OCT", "NOV", "DIC"]

NOTA_APROBATORIA = 11


# ---------- Quién visita ----------


def ip_cliente(request):
    """IP de quien visita. Detrás de IIS u otro proxy en el mismo servidor, la real llega en X-Forwarded-For."""
    ip = request.META.get("REMOTE_ADDR", "")
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if ip in ("127.0.0.1", "::1") and xff:
        ultima = xff.split(",")[-1].strip()
        if re.fullmatch(r"[0-9a-fA-F:.]{3,45}", ultima):
            return ultima
    return ip


def es_https(request):
    """¿Entró por https? Detrás de un proxy local se reconoce por X-Forwarded-Proto."""
    if request.is_secure():
        return True
    local = request.META.get("REMOTE_ADDR", "") in ("127.0.0.1", "::1")
    return local and request.META.get("HTTP_X_FORWARDED_PROTO", "").lower() == "https"


def url_absoluta(request, ruta):
    """Dirección completa (para compartir por WhatsApp). Usa URL_BASE si está configurada."""
    base = getattr(settings, "URL_BASE", "")
    if base:
        return base.rstrip("/") + "/" + ruta.lstrip("/")
    return request.build_absolute_uri(ruta)


def ruta_interna(request, destino, defecto="/"):
    """Solo devuelve rutas de esta aplicación (nunca otro sitio), o `defecto`."""
    prefijo = get_script_prefix().rstrip("/")
    if isinstance(destino, str) and destino.startswith(prefijo + "/") and "//" not in destino and "\\" not in destino:
        return destino
    return defecto


# ---------- Mensajes y páginas ----------


def por_metodo(**vistas):
    """Una misma dirección que hace una cosa con GET (mostrar) y otra con POST (guardar), como en el sistema anterior.

    Uso:  path("admin/ajustes", por_metodo(GET=ver, POST=guardar), name="ajustes")
    """
    from django.http import HttpResponseNotAllowed

    def despachar(request, *args, **kwargs):
        vista_ = vistas.get(request.method) or (vistas.get("GET") if request.method == "HEAD" else None)
        if vista_ is None:
            return HttpResponseNotAllowed(list(vistas))
        return vista_(request, *args, **kwargs)

    return despachar


def recordar_formulario(request):
    """Guarda lo que la persona escribió, para volver a mostrarlo si el formulario vuelve con un error
    (en las plantillas: `{{ old.campo }}`). Los campos en lista (`nombre[]`) se guardan como lista."""
    request.session["_old"] = {
        k: (request.POST.getlist(k) if k.endswith("[]") else request.POST.get(k, ""))
        for k in request.POST
        if k not in ("csrfmiddlewaretoken",)
    }


def volver_con_error(request, ruta, mensaje):
    """Vuelve al formulario con un mensaje de error, recordando lo escrito."""
    from django.shortcuts import redirect

    recordar_formulario(request)
    messages.error(request, mensaje)
    return redirect(ruta)


def ok(request, texto):
    messages.success(request, texto)


def error(request, texto):
    messages.error(request, texto)


def vista(request, plantilla, datos=None, titulo="", sub="", volver=None, menu="inicio", status=200):
    """Muestra una plantilla dentro del marco general. `pagina` lo usa el marco (título, subtítulo, volver, menú)."""
    contexto = dict(datos or {})
    for reservada in ("pagina", "contenido"):
        if reservada in contexto:
            raise ValueError(f"La plantilla {plantilla} no puede recibir la variable «{reservada}» (está reservada).")
    contexto["pagina"] = {"titulo": titulo, "sub": sub, "volver": volver, "menu": menu}
    return render(request, plantilla, contexto, status=status)


def pagina_error(request, mensaje, status):
    return vista(request, "errores/error.html", {"mensaje": mensaje}, titulo="Algo salió mal", menu="", status=status)


def whatsapp_url(telefono):
    """Enlace para escribir por WhatsApp a un teléfono (9 dígitos = Perú), o None si no hay teléfono."""
    n = re.sub(r"\D", "", telefono or "")
    if len(n) < 7:
        return None
    return "https://wa.me/" + ("51" + n if len(n) == 9 else n)


# ---------- Texto ----------


def clave_segura(largo=10):
    """Contraseña temporal segura: letras minúsculas y números sin confusiones (sin 0, o, 1, l, i).
    La persona la cambia al entrar."""
    import secrets

    alfabeto = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(largo))


def plural(n, uno, varios):
    return f"{n} {uno if n == 1 else varios}"


def nota_fmt(nota):
    """Muestra una nota sin decimales innecesarios: 16.00 → 16, 15.50 → 15.5"""
    if nota is None or nota == "":
        return "—"
    return f"{float(nota):.2f}".rstrip("0").rstrip(".")


# ---------- Fechas ----------


def _dt(valor):
    """Fecha y hora con zona (de Lima), a partir de un datetime, una fecha o un texto ISO."""
    if isinstance(valor, datetime):
        pass
    elif isinstance(valor, date):
        valor = datetime(valor.year, valor.month, valor.day)
    else:
        valor = datetime.fromisoformat(str(valor))
    return timezone.localtime(valor) if timezone.is_aware(valor) else timezone.make_aware(valor)


def fecha_larga(valor):
    """«miércoles 7 de octubre»"""
    d = _dt(valor)
    return f"{DIAS[(d.weekday() + 1) % 7]} {d.day} de {MESES[d.month]}"


def fecha_corta(valor):
    """«07/10»"""
    return _dt(valor).strftime("%d/%m")


def hora_texto(valor):
    """«8:30 de la mañana», «11:59 de la noche»"""
    d = _dt(valor)
    parte = "de la mañana" if d.hour < 12 else ("de la tarde" if d.hour < 19 else "de la noche")
    return f"{d.hour % 12 or 12}:{d.minute:02d} {parte}"


def es_hoy(valor):
    return _dt(valor).date() == timezone.localdate()


def mes_corto(valor):
    """«OCT»"""
    return MESES_CORTO[_dt(valor).month]


def vencimiento_texto(limite):
    """Texto de vencimiento pensado para personas: «Vence hoy a las 11:59 de la noche»."""
    lim = _dt(limite)
    ahora = timezone.localtime()
    if lim < ahora:
        return f"La fecha fue el {fecha_larga(lim)}"
    dif = (lim.date() - ahora.date()).days
    if dif == 0:
        return f"Vence hoy a las {hora_texto(lim)}"
    if dif == 1:
        return f"Vence mañana a las {hora_texto(lim)}"
    return f"Vence el {fecha_larga(lim)}"


def tiempo_restante(limite):
    """Tiempo que falta, en palabras: «Faltan 2 horas», «Faltan 3 días», «Venció hace 1 día»."""
    seg = int((_dt(limite) - timezone.localtime()).total_seconds())
    absoluto = abs(seg)
    if absoluto < 3600:
        txt = plural(max(1, absoluto // 60), "minuto", "minutos")
    elif absoluto < 86400:
        txt = plural(absoluto // 3600, "hora", "horas")
    else:
        txt = plural(absoluto // 86400, "día", "días")
    if seg >= 0:
        return ("Falta " if txt.startswith("1 ") else "Faltan ") + txt
    return "Venció hace " + txt


def hace_tiempo(valor):
    """«Hace 5 minutos», «Hace 2 horas», «Ayer»; pasados unos días, la fecha corta."""
    d = _dt(valor)
    seg = max(0, int((timezone.localtime() - d).total_seconds()))
    if seg < 60:
        return "Ahora"
    if seg < 3600:
        return "Hace " + plural(seg // 60, "minuto", "minutos")
    if seg < 86400 and es_hoy(d):
        return "Hace " + plural(seg // 3600, "hora", "horas")
    if d.date() == timezone.localdate() - timedelta(days=1):
        return "Ayer"
    return "Hace " + plural(seg // 86400, "día", "días") if seg < 7 * 86400 else fecha_corta(d)
