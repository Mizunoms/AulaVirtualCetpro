from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("entrar/", views.EntrarView.as_view(), name="entrar"),
    path("salir/", views.salir, name="salir"),
]
