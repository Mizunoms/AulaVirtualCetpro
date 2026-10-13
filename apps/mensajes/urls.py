from django.urls import path

from . import views

app_name = "mensajes"

urlpatterns = [
    path("mensajes", views.index, name="index"),
    path("mensajes/curso/<int:id>", views.modulo, name="modulo"),
    path("mensajes/nuevo", views.nuevo_o_enviar, name="nuevo"),
    path("mensajes/con/<int:curso>/<int:persona>", views.con_o_empezar, name="con"),
    path("mensajes/todos/<int:id>", views.todos_o_enviar, name="todos"),
    path("mensajes/adjunto/<int:id>", views.adjunto, name="adjunto"),
    path("mensajes/<int:id>", views.ver_o_responder, name="ver"),
]
