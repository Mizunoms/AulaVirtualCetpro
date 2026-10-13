from django.urls import path

from . import views, views_admin

app_name = "academico"

urlpatterns = [
    # ----- Docente y alumno -----
    path("cursos", views.modulos_o_guardar, name="modulos"),
    path("cursos/nuevo", views.nuevo, name="nuevo"),
    path("cursos/unirse", views.unirse, name="unirse"),
    path("cursos/<int:id>", views.ver, name="modulo"),
    path("cursos/<int:id>/editar", views.editar_o_actualizar, name="editar"),
    path("cursos/<int:id>/codigo", views.codigo, name="codigo"),
    path("cursos/<int:id>/clases", views.clases_o_crear, name="clases"),
    path("cursos/<int:id>/clases/planificar", views.planificar, name="planificar"),
    path("cursos/<int:id>/nueva", views.nueva_actividad, name="nueva_actividad"),
    path("cursos/<int:id>/eliminar", views.eliminar_o_confirmar, name="eliminar"),
    path("cursos/<int:id>/alumnos", views.alumnos, name="alumnos"),
    path("cursos/<int:id>/alumnos/<int:alumno>/clave", views.clave_alumno, name="clave_alumno"),
    path("cursos/<int:id>/alumnos/<int:alumno>/quitar", views.quitar_alumno, name="quitar_alumno"),
    path("cursos/<int:id>/avisos", views.publicar_aviso, name="publicar_aviso"),
    path("avisos/<int:id>/eliminar", views.eliminar_aviso, name="eliminar_aviso"),
    path("clases/<int:id>", views.clase_o_actualizar, name="clase"),
    path("clases/<int:id>/estado", views.estado_clase, name="estado_clase"),
    path("clases/<int:id>/mover", views.mover_clase, name="mover_clase"),
    path("clases/<int:id>/preguntas", views.preguntar, name="preguntar"),
    path("clases/<int:id>/eliminar", views.eliminar_clase, name="eliminar_clase"),
    path("preguntas-clase/<int:id>/borrar", views.borrar_pregunta, name="borrar_pregunta"),
    # ----- Administración -----
    path("admin/cursos", views_admin.cursos, name="admin_cursos"),
    path("admin/modulos", views_admin.modulos_admin, name="admin_modulos"),
    path("admin/modulos/lote", views_admin.lote, name="admin_lote"),
    path("admin/modulos/nuevo", views_admin.nuevo, name="admin_nuevo"),
    path("admin/modulos/<int:id>", views_admin.actualizar, name="admin_actualizar"),
    path("admin/modulos/<int:id>/editar", views_admin.editar, name="admin_editar"),
    path("admin/modulos/<int:id>/estado", views_admin.estado, name="admin_estado"),
    path("admin/modulos/<int:id>/eliminar", views_admin.confirmar_o_eliminar, name="admin_eliminar"),
    path("admin/modulos/<int:id>/alumnos", views_admin.alumnos_o_matricular, name="admin_alumnos"),
    path("admin/modulos/<int:id>/accesos", views_admin.accesos, name="admin_accesos"),
    path("admin/modulos/<int:id>/alumnos/<int:alumno>/quitar", views_admin.quitar, name="admin_quitar"),
]
