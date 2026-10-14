from django.urls import path

from . import importar_alumnos, importar_docentes, registro, views, views_admin

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
    # Administración de personas
    path("admin/usuarios", views_admin.personas_o_guardar, name="admin_personas"),
    path("admin/usuarios/nuevo", views_admin.nueva, name="admin_nueva_persona"),
    path("admin/usuarios/lote", views_admin.lote, name="admin_lote"),
    path("admin/usuarios/eliminar", views_admin.eliminar, name="admin_eliminar"),
    path("admin/usuarios/claves", views_admin.claves_lote, name="admin_claves"),
    path("admin/usuarios/<int:id>/editar", views_admin.editar, name="admin_editar_persona"),
    path("admin/usuarios/<int:id>", views_admin.actualizar, name="admin_actualizar_persona"),
    path("admin/usuarios/<int:id>/estado", views_admin.estado, name="admin_estado_persona"),
    path("admin/usuarios/<int:id>/clave", views_admin.clave, name="admin_clave_persona"),
    path("admin/alumnos/importar", importar_alumnos.importar_o_procesar, name="admin_importar"),
    path("admin/alumnos/modelo.csv", importar_docentes.modelo_alumnos, name="admin_modelo_alumnos"),
    path("admin/docentes/importar", importar_docentes.importar_o_procesar, name="admin_importar_docentes"),
    path("admin/docentes/modelo.csv", importar_docentes.modelo_docentes, name="admin_modelo_docentes"),
]
