from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .forms import EntrarForm


class EntrarView(LoginView):
    template_name = "cuentas/entrar.html"
    authentication_form = EntrarForm
    redirect_authenticated_user = True


@require_POST
def salir(request):
    logout(request)
    return redirect("cuentas:entrar")
