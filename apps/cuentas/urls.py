from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("login", views.entrar, name="login"),
    path("salir", views.salir, name="salir"),
    path("registro", views.registro_pendiente, name="registro"),
    path("cuenta", views.cuenta, name="cuenta"),
    path("cuenta/preferencias", views.preferencias, name="preferencias"),
    path("cuenta/clave", views.cambiar_clave, name="clave"),
    path("cuenta/nueva-clave", views.nueva_clave, name="nueva_clave"),
]
