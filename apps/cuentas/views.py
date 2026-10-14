"""Entrar, salir y «Mi cuenta». Mismas pantallas, textos y direcciones que el sistema anterior."""

from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.nucleo import ajustes, limites
from apps.nucleo.models import Registro
from apps.nucleo.permisos import exigir
from apps.nucleo.utils import error, ip_cliente, ok, ruta_interna, vista

from .models import Preferencia, Rol, TamanoLetra, Usuario

LARGO_MINIMO_CLAVE = 6


def _entrada(request, clave, defecto=""):
    return (request.POST.get(clave) or defecto).strip()


# ---------- Entrar y salir ----------


def entrar(request):
    """Entrar con DNI (alumno) o con correo (profesor o administrador)."""
    if request.method == "GET":
        if request.user.is_authenticated:
            return redirect("nucleo:inicio")
        old = request.session.get("_old", {})
        como = "personal" if (request.GET.get("como") or old.get("tipo")) == "personal" else "alumno"
        return render(request, "cuentas/login.html", {"como": como, "titulo": "Entrar"})
    return _procesar_entrada(request)


def _procesar_entrada(request):
    usuario = _entrada(request, "usuario")[:120].lower()
    clave = request.POST.get("clave", "")
    tipo = _entrada(request, "tipo")
    volver = reverse("cuentas:login") + ("?como=personal" if tipo == "personal" else "")
    request.session["_old"] = {"usuario": usuario, "tipo": tipo}
    dominio = ajustes.ajuste("dominio_correo")

    # Profesores y administradores: correo del aula; si escriben solo su nombre, se completa con @dominio.
    if tipo == "personal":
        if usuario and "@" not in usuario:
            usuario += "@" + dominio
        if "@" not in usuario:
            error(request, f"Escribe tu correo del aula, por ejemplo profesortecnico@{dominio}.")
            return redirect(volver)
    elif tipo == "alumno" and "@" in usuario:
        error(request, "Si entras con correo, usa la opción «Soy profesor».")
        return redirect(reverse("cuentas:login") + "?como=personal")

    por_cuenta = "login:" + "".join(usuario.split())
    por_ip = "login-ip:" + ip_cliente(request)
    # Muchos intentos fallidos seguidos: se frena esa cuenta 15 minutos (y la red, si son demasiados).
    if limites.superado(por_cuenta, 8, 15) or limites.superado(por_ip, 60, 15):
        error(
            request,
            "Hubo muchos intentos con contraseñas equivocadas. Espera 15 minutos o pide a tu profesor una contraseña nueva.",
        )
        return redirect(volver)

    u = Usuario.objects.buscar_para_entrar(usuario) if usuario else None
    if u is not None and u.rol == Rol.ALUMNO and u.pendiente and u.is_active:
        request.session["_old"] = {"dni": u.dni or ""}
        ok(request, "Todavía no creaste tu contraseña. Confirma tu DNI aquí para crearla.")
        return redirect("cuentas:registro")
    if u is None or u.pendiente or not u.check_password(clave):
        limites.anotar(por_cuenta)
        limites.anotar(por_ip)
        error(
            request,
            ("El correo" if tipo == "personal" else "El DNI") + " o la contraseña no son correctos. Revisa e inténtalo otra vez.",
        )
        return redirect(volver)
    if not u.is_active:
        error(request, "Tu cuenta está desactivada. Pide ayuda en la secretaría del CETPRO.")
        return redirect(volver)

    limites.limpiar(por_cuenta)
    request.session.pop("_old", None)
    return iniciar_y_volver(request, u)


def iniciar_y_volver(request, u, destino=None):
    """Inicia la sesión y vuelve a la página que la persona quería ver (o al inicio)."""
    volver = request.session.pop("_volver_a", None)
    login(request, u, backend="apps.cuentas.backends.DniOCorreoBackend")  # sesión nueva (cambia el identificador)
    request.session.pop("_clave_despues", None)  # un «Más tarde» de antes no vale para esta entrada
    Registro.anotar(u, "acceso", f"{u.nombre_completo} ({u.get_rol_display()}) entró al aula.", request)
    if destino is None:
        return redirect(ruta_interna(request, volver, reverse("nucleo:inicio")))
    return redirect(destino)


@require_POST
def salir(request):
    personal = request.user.is_authenticated and request.user.rol != Rol.ALUMNO
    logout(request)
    ok(request, "Cerraste sesión. ¡Hasta pronto!")
    return redirect(reverse("cuentas:login") + ("?como=personal" if personal else ""))


# ---------- Mi cuenta ----------


@exigir()
def cuenta(request):
    return vista(request, "cuentas/cuenta.html", {"u": request.user}, titulo="Mi cuenta", sub="Ajustes y salir", menu="cuenta")


@require_POST
@exigir()
def preferencias(request):
    u = request.user
    letra = _entrada(request, "tamano_letra")
    Preferencia.objects.update_or_create(
        usuario=u,
        defaults={
            "tamano_letra": letra if letra in TamanoLetra.values else TamanoLetra.NORMAL,
            "alto_contraste": "alto_contraste" in request.POST,
            "lectura_voz": "lectura_voz" in request.POST,
            "reducir_movimiento": "reducir_movimiento" in request.POST,
        },
    )
    respuesta = redirect("cuentas:cuenta")
    ok(request, "Listo, guardamos tus cambios.")
    guardar_tema(respuesta, _entrada(request, "tema"))
    return respuesta


def guardar_tema(respuesta, tema):
    """Recuerda el modo claro/oscuro en una cookie de este dispositivo."""
    respuesta.set_cookie(
        "aula_tema", "oscuro" if tema == "oscuro" else "claro", max_age=365 * 86400, httponly=True, samesite="Lax"
    )


@require_POST
@exigir()
def cambiar_clave(request):
    u = request.user
    actual, nueva, repetir = (request.POST.get(k, "") for k in ("actual", "nueva", "repetir"))
    destino = reverse("cuentas:cuenta") + "#clave"
    if not u.check_password(actual):
        error(request, "Tu contraseña actual no es correcta.")
        return redirect(destino)
    if len(nueva) < LARGO_MINIMO_CLAVE:
        error(request, "La contraseña nueva debe tener al menos 6 letras o números.")
        return redirect(destino)
    if nueva != repetir:
        error(request, "Las dos contraseñas nuevas no son iguales.")
        return redirect(destino)
    guardar_clave_propia(request, u, nueva)
    Registro.anotar(u, "clave", f"{u.nombre_completo} cambió su propia contraseña.", request)
    ok(request, "Tu contraseña se cambió. Úsala la próxima vez que entres.")
    return redirect("cuentas:cuenta")


def guardar_clave_propia(request, u, nueva):
    """Cambia la contraseña de la persona y mantiene abierta su sesión."""
    from django.contrib.auth import update_session_auth_hash

    u.set_password(nueva)
    u.debe_cambiar_clave = False
    u.save(update_fields=["password", "debe_cambiar_clave"])
    update_session_auth_hash(request, u)


@exigir()
def nueva_clave(request):
    """Primera vez con una contraseña temporal: elige la suya."""
    u = request.user
    if request.method == "POST":
        if "despues" in request.POST:
            return _dejar_para_despues(request, u)
        return _guardar_nueva_clave(request, u)
    if not u.debe_cambiar_clave:
        return redirect("cuentas:cuenta")
    # Si viene de «Crear mi cuenta», se le muestra también la contraseña temporal (por si cierra la página).
    reciente = request.session.get("_registro_listo")
    temporal = (
        reciente["clave"] if isinstance(reciente, dict) and reciente.get("t", 0) > timezone.now().timestamp() - 1800 else None
    )
    return vista(
        request,
        "cuentas/nueva_clave.html",
        {"u": u, "temporal": temporal},
        titulo="¡Tu cuenta está lista!" if temporal else "Elige tu contraseña",
        sub="Paso 3 de 3" if temporal else "Solo esta vez",
        menu="cuenta",
    )


def _dejar_para_despues(request, u):
    """«Más tarde»: sigue dentro del aula (no se cierra la sesión). La contraseña temporal sigue valiendo, así que arriba
    queda el aviso con el botón «Crear mi nueva contraseña», y al volver a entrar se le pide otra vez."""
    if not u.debe_cambiar_clave:
        return redirect("cuentas:cuenta")
    request.session["_clave_despues"] = True
    ok(request, "Está bien, lo haces más tarde. Cuando quieras, toca «Crear mi nueva contraseña» (está arriba).")
    return redirect("nucleo:inicio")


def _guardar_nueva_clave(request, u):
    if not u.debe_cambiar_clave:
        # Sin contraseña temporal, para cambiarla hay que escribir la actual (ver «Cambiar mi contraseña» en Mi cuenta).
        error(request, "Para cambiar tu contraseña escribe primero la actual.")
        return redirect("cuentas:cuenta")
    nueva, repetir = request.POST.get("nueva", ""), request.POST.get("repetir", "")
    destino = reverse("cuentas:nueva_clave")
    if len(nueva) < LARGO_MINIMO_CLAVE:
        error(request, "La contraseña nueva debe tener al menos 6 letras o números.")
        return redirect(destino)
    if nueva != repetir:
        error(request, "Las dos contraseñas no son iguales.")
        return redirect(destino)
    if u.check_password(nueva) or (u.dni or "") == nueva:
        error(request, "Elige una contraseña distinta de la que te dieron y que no sea tu DNI.")
        return redirect(destino)
    guardar_clave_propia(request, u, nueva)
    Registro.anotar(u, "clave", f"{u.nombre_completo} eligió su contraseña nueva al entrar.", request)
    request.session.pop("_registro_listo", None)
    request.session.pop("_clave_despues", None)
    ok(request, "¡Listo! Ya puedes usar el aula. Esta es tu contraseña desde ahora.", celebrar=True)
    return redirect("nucleo:inicio")
