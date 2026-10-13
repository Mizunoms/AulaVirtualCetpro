from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm

from .models import Usuario


class UsuarioCreationForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("correo", "nombres", "rol")


class UsuarioChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"


class EntrarForm(AuthenticationForm):
    username = forms.CharField(
        label="DNI o correo",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username", "inputmode": "email"}),
    )
    password = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    error_messages = {
        "invalid_login": "El DNI, el correo o la contraseña no son correctos.",
        "inactive": "Esta cuenta está desactivada. Pide ayuda en secretaría.",
    }
