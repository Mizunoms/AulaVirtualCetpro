"""Formularios del panel técnico de Django (las pantallas del aula usan formularios HTML propios)."""

from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import Usuario


class UsuarioCreationForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("correo", "nombres", "rol")


class UsuarioChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"
