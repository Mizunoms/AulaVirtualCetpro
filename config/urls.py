from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("apps.nucleo.urls")),
    path("", include("apps.cuentas.urls")),
    # Panel técnico de Django: solo para quien administra el sistema (no es el panel del CETPRO).
    path("django-admin/", admin.site.urls),
]
