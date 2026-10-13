"""«Crear mi cuenta» de los alumnos, con su DNI.

1. Escribe su DNI.
2a. Si el CETPRO ya lo cargó en una lista: confirma que es él/ella (y su fecha de nacimiento, si la tenemos).
2b. Si no: escribe el código del módulo que le dio su profesor y sus datos.
3. Se le da una contraseña temporal y enseguida elige la suya (ver `views.nueva_clave`).
"""

import re
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.academico.models import Modulo
from apps.nucleo import ajustes, limites
from apps.nucleo.permisos import exigir
from apps.nucleo.utils import clave_segura, error, ip_cliente, ok, por_metodo, volver_con_error

from .models import Origen, Preferencia, Rol, TamanoLetra, Usuario

VENCE_SEGUNDOS = 1800  # los datos del registro en curso se vencen a los 30 minutos


def _entrada(request, clave):
    return (request.POST.get(clave) or "").strip()


_con_error = volver_con_error


def _paso(request, tipo):
    """Datos del registro en curso. Devuelve (datos, None) o (None, redirección)."""
    r = request.session.get("_registro")
    if not isinstance(r, dict) or r.get("tipo") != tipo or r.get("t", 0) < timezone.now().timestamp() - VENCE_SEGUNDOS:
        request.session.pop("_registro", None)
        ok(request, "Empieza escribiendo tu DNI.")
        return None, redirect("cuentas:registro")
    return r, None


def _nombre(texto):
    """«rosa maría» → «Rosa María»; vacío si trae algo raro (solo letras, espacios, punto, apóstrofo y guion)."""
    texto = re.sub(r"\s+", " ", texto or "").strip()
    if not texto or len(texto) > 100 or not texto[0].isalpha() or not all(c.isalpha() or c in " .'-" for c in texto):
        return ""
    return texto.lower().title()


def _fecha(texto):
    """Fecha AAAA-MM-DD válida (entre 1920 y hace 10 años), o None."""
    try:
        d = date.fromisoformat(texto)
    except ValueError:
        return None
    return d if date(1920, 1, 1) <= d <= date.today() - timedelta(days=3652) else None


def _celular(texto):
    return re.sub(r"\D", "", texto or "")[:15]


def _terminar(request, usuario, clave):
    from .views import iniciar_y_volver

    request.session.pop("_registro", None)
    request.session.pop("_old", None)
    request.session["_registro_listo"] = {"clave": clave, "t": timezone.now().timestamp()}
    return iniciar_y_volver(request, usuario, destino=reverse("cuentas:nueva_clave"))


# ---------- Paso 1: el DNI ----------


def inicio(request):
    if request.user.is_authenticated:
        return redirect("nucleo:inicio")
    request.session.pop("_registro", None)
    return render(
        request, "cuentas/registro/dni.html", {"abierto": ajustes.ajuste("registro_abierto") == "1", "titulo": "Crear mi cuenta"}
    )


def revisar_dni(request):
    dni = re.sub(r"\D", "", _entrada(request, "dni"))
    request.session["_old"] = {"dni": dni}
    if len(dni) != 8:
        error(request, "El DNI tiene 8 números. Revísalo e inténtalo otra vez.")
        return redirect("cuentas:registro")
    por_ip = "dni-ip:" + ip_cliente(request)
    if limites.superado(por_ip, 60, 15):
        error(request, "Se revisaron muchos DNI desde esta red. Espera unos minutos e inténtalo otra vez.")
        return redirect("cuentas:registro")
    limites.anotar(por_ip)

    u = Usuario.objects.filter(dni=dni).first()
    if u is not None and not u.pendiente and u.is_active:
        request.session["_old"] = {"usuario": dni}
        ok(request, "Ya tienes tu cuenta. Entra con tu DNI y tu contraseña. Si la olvidaste, pide a tu profesor una nueva.")
        return redirect("cuentas:login")
    if u is not None and (u.rol != Rol.ALUMNO or not u.is_active):
        error(request, "Con ese DNI no se puede crear una cuenta aquí. Pide ayuda en la secretaría del CETPRO.")
        return redirect("cuentas:registro")
    ahora = timezone.now().timestamp()
    if u is not None:
        request.session["_registro"] = {"dni": dni, "tipo": "lista", "id": u.pk, "t": ahora}
        return redirect("cuentas:registro_confirmar")
    if ajustes.ajuste("registro_abierto") != "1":
        error(request, "Tu DNI no está en la lista del CETPRO. Pide en la secretaría que te registren.")
        return redirect("cuentas:registro")
    request.session["_registro"] = {"dni": dni, "tipo": "nuevo", "t": ahora}
    return redirect("cuentas:registro_datos")


# ---------- Paso 2b: alumno nuevo con el código del módulo ----------


def datos(request):
    r, redireccion = _paso(request, "nuevo")
    if redireccion:
        return redireccion
    return render(
        request,
        "cuentas/registro/datos.html",
        {"dni": r["dni"], "titulo": "Tus datos", "max_nacimiento": (date.today() - timedelta(days=3652)).isoformat()},
    )


def guardar_datos(request):
    r, redireccion = _paso(request, "nuevo")
    if redireccion:
        return redireccion
    ip = ip_cliente(request)
    volver = reverse("cuentas:registro_datos")
    nombres, apellidos = _nombre(_entrada(request, "nombres")), _nombre(_entrada(request, "apellidos"))
    telefono = _celular(_entrada(request, "telefono"))
    nacimiento_texto = _entrada(request, "fecha_nacimiento")
    nacimiento = _fecha(nacimiento_texto)
    if not nombres or not apellidos:
        return _con_error(request, volver, "Escribe tus nombres y tus apellidos (solo letras).")
    if telefono and len(telefono) != 9:
        return _con_error(request, volver, "El celular tiene 9 números. Revísalo o déjalo vacío.")
    if nacimiento_texto and nacimiento is None:
        return _con_error(request, volver, "Revisa tu fecha de nacimiento.")
    if limites.superado("codigo-ip:" + ip, 15, 15):
        return _con_error(request, volver, "Hubo muchos códigos equivocados desde esta red. Espera 15 minutos.")
    modulo = Modulo.por_codigo(_entrada(request, "codigo"))
    if modulo is None:
        limites.anotar("codigo-ip:" + ip)
        return _con_error(
            request, volver, "Ese código no es correcto. Pide a tu profesor el código de tu módulo (por ejemplo: PEL-4821)."
        )
    if not modulo.inscripcion_abierta:
        return _con_error(request, volver, "Ese módulo ya no acepta alumnos nuevos. Habla con tu profesor.")
    if limites.superado("registro-ip:" + ip, 80, 60):
        return _con_error(request, volver, "Se crearon muchas cuentas desde esta red. Espera un rato e inténtalo otra vez.")

    clave = clave_segura()  # temporal: enseguida elige la suya
    try:
        with transaction.atomic():
            alumno = Usuario.objects.crear_alumno(
                r["dni"], nombres, apellidos, clave=clave, origen=Origen.REGISTRO, telefono=telefono, fecha_nacimiento=nacimiento
            )
    except IntegrityError:
        request.session.pop("_registro", None)
        ok(request, "Ese DNI ya tiene cuenta. Entra con tu DNI y tu contraseña.")
        return redirect("cuentas:login")
    alumno.debe_cambiar_clave = True
    alumno.save(update_fields=["debe_cambiar_clave"])
    limites.anotar("registro-ip:" + ip)
    modulo.matricular(alumno)
    if "letra_grande" in request.POST:
        Preferencia.objects.update_or_create(usuario=alumno, defaults={"tamano_letra": TamanoLetra.GRANDE})
    return _terminar(request, alumno, clave)


# ---------- Paso 2a: alumno que ya estaba en la lista del CETPRO ----------


def confirmar(request):
    r, redireccion = _paso(request, "lista")
    if redireccion:
        return redireccion
    u = Usuario.objects.filter(pk=r["id"]).first()
    if u is None:
        return redirect("cuentas:registro")
    modulos = Modulo.objects.de_alumno(u).order_by("nombre")
    return render(
        request,
        "cuentas/registro/confirmar.html",
        {
            "nombre": f"{u.primer_nombre} {u.apellidos.strip()[:1]}.",
            "pide_fecha": u.fecha_nacimiento is not None,
            "modulos": modulos,
            "titulo": "Confirma que eres tú",
        },
    )


def guardar_confirmar(request):
    r, redireccion = _paso(request, "lista")
    if redireccion:
        return redireccion
    u = Usuario.objects.filter(pk=r["id"]).first()
    if u is None or not u.pendiente:
        request.session.pop("_registro", None)
        ok(request, "Tu cuenta ya tiene contraseña. Entra con tu DNI.")
        return redirect("cuentas:login")
    volver = reverse("cuentas:registro_confirmar")
    if u.fecha_nacimiento is not None:
        clave_limite = "nacimiento:" + r["dni"]
        if limites.superado(clave_limite, 5, 30):
            return _con_error(request, volver, "Hubo muchos intentos. Pide ayuda en la secretaría o a tu profesor.")
        if _fecha(_entrada(request, "fecha_nacimiento")) != u.fecha_nacimiento:
            limites.anotar(clave_limite)
            return _con_error(request, volver, "La fecha de nacimiento no coincide con la que tiene el CETPRO. Revísala.")
    telefono = _celular(_entrada(request, "telefono"))
    if telefono and len(telefono) != 9:
        return _con_error(request, volver, "El celular tiene 9 números. Revísalo o déjalo vacío.")
    clave = clave_segura()  # temporal: enseguida elige la suya
    u.activar(clave, telefono)
    u.debe_cambiar_clave = True
    u.save(update_fields=["debe_cambiar_clave"])
    if "letra_grande" in request.POST:
        Preferencia.objects.update_or_create(usuario=u, defaults={"tamano_letra": TamanoLetra.GRANDE})
    return _terminar(request, u, clave)


@exigir(Rol.ALUMNO)
def listo(request):
    """Antes aquí se mostraba la contraseña; ahora el paso 3 es elegir la propia (ver `views.nueva_clave`)."""
    return redirect("nucleo:inicio")


registro_dni = por_metodo(GET=inicio, POST=revisar_dni)
registro_datos = por_metodo(GET=datos, POST=guardar_datos)
registro_confirmar = por_metodo(GET=confirmar, POST=guardar_confirmar)
