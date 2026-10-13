"""Dibujo del taller (solo adorno) para la portada de un módulo que todavía no tiene foto."""

import re
import unicodedata

from django.utils.safestring import mark_safe

DIBUJOS = {
    "tijeras": '<circle cx="36" cy="98" r="11"/><circle cx="68" cy="98" r="11"/><path d="M42 89L84 24M62 89L20 24"/><rect x="78" y="52" width="34" height="12" rx="3"/><path d="M84 64v10M92 64v10M100 64v10M108 64v10"/>',
    "pan": '<path d="M16 80C16 52 38 34 60 34s44 18 44 46z"/><path d="M16 80h88v12q0 6-6 6H22q-6 0-6-6z"/><path d="M42 50l-6 16M60 46l-6 18M78 50l-6 16"/>',
    "costura": '<path d="M30 30h44M30 98h44M36 30v68M68 30v68M36 46h32M36 60h32M36 74h32"/><path d="M92 18l10 88"/><ellipse cx="93" cy="28" rx="2" ry="6"/><path d="M68 98c18 8 10-14 26-10"/>',
    "monitor": '<rect x="14" y="24" width="92" height="60" rx="7"/><path d="M46 100h28M60 84v16M30 44l10 8-10 8M50 62h22"/>',
    "soldadura": '<path d="M18 104l44-48"/><path d="M68 52q10-24 26-30-2 14 8 22-12 4-16 18-8-4-18-10z"/><path d="M86 76l12 6M78 88l8 16M100 60l10-3"/>',
    "artesania": '<path d="M46 22h28"/><path d="M50 22c0 14-24 20-24 44 0 20 14 32 34 32s34-12 34-32c0-24-24-30-24-44"/><path d="M28 64h64M30 78h60"/>',
    "cultivo": '<path d="M60 104V50"/><path d="M60 72C60 52 40 44 24 48 24 64 40 74 60 72"/><path d="M60 58C60 40 78 30 96 34 96 52 80 62 60 58"/>',
    "joyeria": '<path d="M36 40h48l16 20-40 46-40-46z"/><path d="M20 60h80M48 40l12 20 12-20M60 60v46"/>',
    "general": '<path d="M60 28L14 52l46 24 46-24z"/><path d="M32 63v22c0 9 56 9 56 0V63M106 52v28"/>',
}

# (patrón sobre el nombre del curso sin tildes, dibujo)
_REGLAS = [
    (r"peluquer|barber|estetic|cosmet", "tijeras"),
    (r"panader|pasteler|cocina|gastronom", "pan"),
    (r"costur|confecc|textil|acabado", "costura"),
    (r"soporte|comput|inform|electr", "monitor"),
    (r"soldad|metal|mecanic", "soldadura"),
    (r"artesan|manualid", "artesania"),
    (r"cultiv|agricol|agrop", "cultivo"),
    (r"joyer", "joyeria"),
]


def _sin_tildes(texto):
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def dibujo_taller(especialidad):
    e = _sin_tildes(especialidad)
    clave = next((d for patron, d in _REGLAS if re.search(patron, e)), "general")
    return mark_safe(  # noqa: S308 - los trazos son fijos, escritos por nosotros
        '<svg class="dibujo-taller" viewBox="0 0 120 120" fill="none" stroke="currentColor" stroke-width="3" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + DIBUJOS[clave] + "</svg>"
    )
