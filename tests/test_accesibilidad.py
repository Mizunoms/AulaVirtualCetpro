"""Accesibilidad básica del HTML: identificadores únicos y etiquetas que apuntan al campo correcto."""

from html.parser import HTMLParser

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class Revisor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.para, self.dentro_de_label, self.marcas_sin_label = [], [], 0, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.append(a["id"])
        if tag == "label":
            self.dentro_de_label += 1
            if a.get("for"):
                self.para.append(a["for"])
        if tag == "input" and a.get("type") == "checkbox" and not self.dentro_de_label and "form" in a:
            self.marcas_sin_label.append(a.get("aria-label", ""))  # casilla de lista (selección en lote) sin zona de toque

    def handle_endtag(self, tag):
        if tag == "label":
            self.dentro_de_label -= 1


def revisar(html):
    r = Revisor()
    r.feed(html)
    repetidos = sorted({i for i in r.ids if r.ids.count(i) > 1})
    sin_campo = sorted({p for p in r.para if p not in r.ids})
    return repetidos, sin_campo, r.marcas_sin_label


def pagina(cliente, url):
    r = cliente.get(url)
    assert r.status_code == 200, url
    return r.content.decode()


def test_ninguna_pantalla_repite_identificadores_ni_deja_etiquetas_sueltas(
    client, cliente_de, docente, admin, rosa, modulo, clase
):
    paginas = [
        (client, reverse("cuentas:login")),
        (cliente_de(rosa), reverse("nucleo:inicio")),
        (cliente_de(rosa), reverse("academico:modulo", args=[modulo.pk])),
        (cliente_de(docente), reverse("academico:modulo", args=[modulo.pk])),  # aquí está «Escribir un aviso»
        (cliente_de(docente), reverse("academico:clase", args=[clase.pk])),
        (cliente_de(admin), reverse("cuentas:admin_personas")),
        (cliente_de(admin), "/admin/modulos"),
    ]
    for cliente, url in paginas:
        repetidos, sin_campo, _ = revisar(pagina(cliente, url))
        assert not repetidos, f"{url}: identificadores repetidos {repetidos}"
        assert not sin_campo, f"{url}: etiquetas que apuntan a un campo que no existe {sin_campo}"


def test_el_aviso_del_modulo_tiene_su_etiqueta_bien_enlazada(cliente_de, docente, modulo):
    html = pagina(cliente_de(docente), reverse("academico:modulo", args=[modulo.pk]))
    assert 'for="aviso-contenido"' in html and 'id="aviso-contenido"' in html
    assert html.count('id="contenido"') == 1  # solo la zona principal (el enlace «Saltar al contenido»)


def test_las_casillas_de_seleccion_en_lote_estan_dentro_de_una_etiqueta_grande(cliente_de, admin, rosa):
    _, _, sueltas = revisar(pagina(cliente_de(admin), reverse("cuentas:admin_personas")))
    assert not sueltas, f"casillas sin etiqueta que les dé una zona de toque de 44 px: {sueltas}"
