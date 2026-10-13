from django.urls import path

from . import registro, views, views_admin

app_name = "cuentas"

urlpatterns = [
    path("login", views.entrar, name="login"),
    path("salir", views.salir, name="salir"),
    path("registro", registro.registro_dni, name="registro"),
    path("registro/datos", registro.registro_datos, name="registro_datos"),
    path("registro/confirmar", registro.registro_confirmar, name="registro_confirmar"),
    path("registro/listo", registro.listo, name="registro_listo"),
    path("cuenta", views.cuenta, name="cuenta"),
    path("cuenta/preferencias", views.preferencias, name="preferencias"),
    path("cuenta/clave", views.cambiar_clave, name="clave"),
    path("cuenta/nueva-clave", views.nueva_clave, name="nueva_clave"),
    path("admin/usuarios/claves", views_admin.claves_lote, name="admin_claves"),
]
