"""Frena a quien prueba muchas contraseñas, DNI o códigos seguidos."""

import random
from datetime import timedelta

from django.utils import timezone

from .models import IntentoAcceso


def cuenta(clave, minutos):
    desde = timezone.now() - timedelta(minutes=minutos)
    return IntentoAcceso.objects.filter(clave=clave[:100], creado__gt=desde).count()


def superado(clave, maximo, minutos):
    """¿Ya hubo `maximo` intentos con esta clave en los últimos `minutos`?"""
    return cuenta(clave, minutos) >= maximo


def anotar(clave):
    IntentoAcceso.objects.create(clave=clave[:100])
    if random.randint(1, 50) == 1:  # limpieza ocasional de lo viejo
        IntentoAcceso.objects.filter(creado__lt=timezone.now() - timedelta(days=1)).delete()


def limpiar(clave):
    IntentoAcceso.objects.filter(clave=clave[:100]).delete()
