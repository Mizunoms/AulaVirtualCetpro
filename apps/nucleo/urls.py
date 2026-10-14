from django.urls import path

from . import views
from .utils import por_metodo

app_name = "nucleo"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("tema", views.tema, name="tema"),
    path("ayuda", views.ayuda_ver, name="ayuda"),
    path("notificaciones", views.avisos, name="avisos"),
    path("marca/logo", views.marca_logo, name="marca_logo"),
    path("marca/fondo", views.marca_fondo, name="marca_fondo"),
    path("marca/especialidad", views.marca_especialidad, name="marca_especialidad"),
    path("admin/ajustes", por_metodo(GET=views.ajustes_ver, POST=views.ajustes_guardar), name="ajustes"),
    path("admin/ajustes/imagen", views.ajustes_imagen, name="ajustes_imagen"),
    path("admin/ajustes/foto", views.ajustes_foto, name="ajustes_foto"),
    path("admin/ajustes/especialidades", views.ajustes_especialidades, name="ajustes_especialidades"),
    path("admin/registro", views.registro, name="registro"),
]
