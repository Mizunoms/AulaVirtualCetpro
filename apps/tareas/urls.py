from django.urls import path

from apps.nucleo.utils import por_metodo

from . import views

app_name = "tareas"

urlpatterns = [
    # Materiales
    path("cursos/<int:id>/materiales", views.material_guardar, name="material_guardar"),
    path("materiales/<int:id>", views.material_ver, name="material"),
    path("materiales/<int:id>/eliminar", views.material_eliminar, name="material_eliminar"),
    # Tareas
    path("cursos/<int:id>/tareas", por_metodo(GET=views.index, POST=views.guardar), name="modulo"),
    path("cursos/<int:id>/tareas/nueva", views.crear, name="nueva"),
    path("tareas/<int:id>", views.ver, name="ver"),
    path("tareas/<int:id>/entregar", views.entregar, name="entregar"),
    path("tareas/<int:id>/archivo", views.archivo_de_tarea, name="archivo"),
    path("tareas/<int:id>/eliminar", views.eliminar, name="eliminar"),
    # Calificar
    path("por-calificar", views.por_calificar, name="por_calificar"),
    path("entregas/<int:id>", views.calificar_o_guardar, name="calificar"),
    path("entregas/<int:id>/archivo", views.entrega_archivo, name="entrega_archivo"),
    path("entregas/<int:id>/retro", views.entrega_retro, name="entrega_retro"),
]
