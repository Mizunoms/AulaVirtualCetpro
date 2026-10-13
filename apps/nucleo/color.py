"""Cálculos de color para el tema del aula (contraste WCAG y tonos claros/oscuros)."""

import re

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def valido(hex_):
    return bool(_HEX.match(hex_ or ""))


def rgb(hex_):
    h = hex_.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def a_hex(canales):
    r, g, b = (max(0, min(255, round(c))) for c in canales)
    return f"#{r:02X}{g:02X}{b:02X}"


def mezclar(hex_, otro, peso):
    """Mezcla con otro color: `peso` = cuánto del otro (0 a 1)."""
    a, b = rgb(hex_), rgb(otro)
    return a_hex([a[i] + (b[i] - a[i]) * peso for i in range(3)])


def luminancia(hex_):
    def canal(v):
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(v) for v in rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    la, lb = luminancia(a), luminancia(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
