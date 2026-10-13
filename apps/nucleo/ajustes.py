"""Ajustes del aula que cambia el administrador desde el panel (colores, logo, textos, especialidades…).

Se leen con `ajuste("clave")`. Si una clave no está guardada, se usa su valor por defecto.
"""

import json
from datetime import date

from django.core.cache import cache

from . import color

DEFECTO = {
    "centro_nombre": "CETPRO Mangomarca",
    "aula_nombre": "Aula Virtual",
    "bienvenida": "Aprende a tu ritmo, desde tu celular o tu computadora.",
    "color_principal": "#0B1B35",
    "color_acento": "#C8231B",
    "color_secundario": "#1249A3",
    "logo": "",
    "fondo_login": "",
    "aviso_general": "",
    "whatsapp": "",
    "telefono": "",
    "horario_atencion": "",
    "web": "",
    "reglamento_url": "",
    "horario_url": "",
    "registro_abierto": "1",
    "dominio_correo": "cetpro.com",  # correo de docentes y admin: nombre@cetpro.com
    "periodo": "",
    "especialidades": "",
}

ESPECIALIDADES = [
    {"nombre": "Soporte Técnico", "color": "#1249A3"},
    {"nombre": "Soldadura Universal", "color": "#55627F"},
    {"nombre": "Artesanía y Manualidades", "color": "#9A3412"},
    {"nombre": "Técnicas de Cultivo Agrícolas", "color": "#166534"},
    {"nombre": "Diseño de Piezas de Joyería", "color": "#7E22CE"},
    {"nombre": "Peluquería y Barbería", "color": "#C8231B"},
    {"nombre": "Panadería y Pastelería", "color": "#B45309"},
    {"nombre": "Costura y Acabados", "color": "#0E7490"},
]

_CLAVE_CACHE = "aula_ajustes"


def todas():
    """Todos los ajustes (los guardados encima de los valores por defecto)."""
    from .models import Ajuste

    valores = cache.get(_CLAVE_CACHE)
    if valores is None:
        valores = dict(DEFECTO)
        valores.update(dict(Ajuste.objects.values_list("clave", "valor")))
        if valores["periodo"] == "":
            hoy = date.today()
            valores["periodo"] = f"{hoy.year}-{'II' if hoy.month >= 8 else 'I'}"
        cache.set(_CLAVE_CACHE, valores, 300)
    return valores


def ajuste(clave):
    return str(todas().get(clave, ""))


def guardar(valores):
    """Guarda varios ajustes a la vez (solo claves conocidas)."""
    from .models import Ajuste

    for clave, valor in valores.items():
        if clave in DEFECTO:
            Ajuste.objects.update_or_create(clave=clave, defaults={"valor": str(valor)})
    cache.delete(_CLAVE_CACHE)


def especialidades():
    """Especialidades con su color: [{"nombre": …, "color": …}, …]"""
    try:
        lista = json.loads(ajuste("especialidades") or "[]")
    except ValueError:
        lista = []
    return lista if isinstance(lista, list) and lista else [dict(e) for e in ESPECIALIDADES]


def guardar_especialidades(lista):
    guardar({"especialidades": json.dumps(list(lista), ensure_ascii=False)})


def nombres_especialidades():
    return [e["nombre"] for e in especialidades()]


def color_curso(especialidad):
    for esp in especialidades():
        if esp["nombre"] == especialidad:
            return esp["color"]
    return ajuste("color_principal") or "#0B1B35"


def tema_css():
    """Variables CSS con los colores elegidos en Ajustes (y sus tonos claros y oscuros)."""
    principal, acento, secundario = ajuste("color_principal"), ajuste("color_acento"), ajuste("color_secundario")
    if not (color.valido(principal) and color.valido(acento) and color.valido(secundario)):
        return ""
    variables = {
        "--navy": principal,
        "--navy-2": color.mezclar(principal, "#FFFFFF", 0.12),
        "--rojo": acento,
        "--rojo-oscuro": color.mezclar(acento, "#000000", 0.2),
        "--rojo-claro": color.mezclar(acento, "#FFFFFF", 0.9),
        "--azul": secundario,
        "--azul-oscuro": color.mezclar(secundario, "#000000", 0.25),
        "--azul-claro": color.mezclar(secundario, "#FFFFFF", 0.88),
    }
    return ":root{" + "".join(f"{k}:{v};" for k, v in variables.items()) + "}"
