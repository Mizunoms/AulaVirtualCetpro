from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import UsuarioChangeForm, UsuarioCreationForm
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Vista técnica de las cuentas. El panel de personas del CETPRO es otra pantalla (fase 4)."""

    form = UsuarioChangeForm
    add_form = UsuarioCreationForm

    list_display = ("nombre_completo", "dni", "correo", "rol", "is_active")
    list_filter = ("rol", "is_active")
    search_fields = ("dni", "correo", "nombres", "apellidos")
    ordering = ("apellidos", "nombres")
    fieldsets = (
        (None, {"fields": ("correo", "password")}),
        ("Datos", {"fields": ("dni", "nombres", "apellidos", "telefono", "fecha_nacimiento", "rol")}),
        ("Permisos", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("correo", "nombres", "rol", "password1", "password2")}),
    )
