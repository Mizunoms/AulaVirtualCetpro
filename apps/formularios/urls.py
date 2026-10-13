from django.urls import path

from . import views, views_importar, views_intentos

app_name = "formularios"

urlpatterns = [
    # El formulario
    path("cursos/<int:id>/examenes/nuevo", views.nuevo, name="nuevo"),
    path("cursos/<int:id>/examenes", views.guardar, name="guardar"),
    path("examenes/plantilla", views.plantilla, name="plantilla"),
    path("examenes/<int:id>", views.ver, name="ver"),
    path("examenes/<int:id>/editar", views.editar_o_actualizar, name="editar"),
    path("examenes/<int:id>/publicar", views.publicar, name="publicar"),
    path("examenes/<int:id>/eliminar", views.eliminar, name="eliminar"),
    path("examenes/<int:id>/preguntas", views.agregar_pregunta, name="agregar_pregunta"),
    path("examenes/<int:id>/resultados", views.resultados, name="resultados"),
    path("examenes/<int:id>/descargar", views.descargar, name="descargar"),
    path("examenes/<int:id>/vista-previa", views.vista_previa, name="vista_previa"),
    path("examenes/<int:id>/importar", views_importar.importar_o_procesar, name="importar"),
    path("examenes/<int:id>/importar/confirmar", views_importar.confirmar, name="importar_confirmar"),
    # Las preguntas
    path("preguntas/<int:id>/duplicar", views.duplicar_pregunta, name="pregunta_duplicar"),
    path("preguntas/<int:id>/imagen", views.imagen_de_pregunta, name="pregunta_imagen"),
    path("preguntas/<int:id>/editar", views.editar_pregunta, name="pregunta_editar"),
    path("preguntas/<int:id>", views.actualizar_pregunta, name="pregunta_actualizar"),
    path("preguntas/<int:id>/eliminar", views.eliminar_pregunta, name="pregunta_eliminar"),
    path("preguntas/<int:id>/mover", views.mover_pregunta, name="pregunta_mover"),
    # El alumno responde y el docente revisa
    path("examenes/<int:id>/empezar", views_intentos.empezar, name="empezar"),
    path("intentos/<int:id>", views_intentos.intento_o_entregar, name="intento"),
    path("intentos/<int:id>/revisar", views_intentos.revisar, name="revisar"),
    path("respuestas/<int:id>/archivo", views_intentos.archivo_de_respuesta, name="respuesta_archivo"),
]
