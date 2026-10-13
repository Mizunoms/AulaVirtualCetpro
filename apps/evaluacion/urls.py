from django.urls import path

from . import views

app_name = "evaluacion"

urlpatterns = [
    path("cursos/<int:id>/asistencia", views.asistencia_o_guardar, name="asistencia"),
    path("notas", views.mis_notas, name="mis_notas"),
    path("cursos/<int:id>/notas", views.notas_modulo, name="notas_modulo"),
    path("cursos/<int:id>/notas/pesos", views.notas_pesos, name="notas_pesos"),
    path("cursos/<int:id>/notas/excel", views.notas_excel, name="notas_excel"),
    path("cursos/<int:id>/notas/imprimir", views.notas_imprimir, name="notas_imprimir"),
    path("admin/reportes/consolidado", views.consolidado, name="consolidado"),
]
