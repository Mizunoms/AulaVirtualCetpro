"""Cabeceras de seguridad: el navegador solo carga lo propio del aula, Bootstrap y las letras de Google."""

CSP = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; media-src 'self' blob:; "
    "connect-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; object-src 'none'"
)


class CabecerasSeguridad:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        respuesta.headers.setdefault("Referrer-Policy", "same-origin")
        respuesta.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=(self), payment=()")
        # El panel técnico de Django usa scripts propios dentro de la página: no se le aplica esta política.
        if not request.path.startswith("/django-admin"):
            respuesta.headers.setdefault("Content-Security-Policy", CSP)
        return respuesta
