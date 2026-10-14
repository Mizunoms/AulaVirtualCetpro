"""Accesibilidad básica del HTML: identificadores únicos y etiquetas que apuntan al campo correcto."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

RAIZ = Path(__file__).resolve().parent.parent


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


# ===================================================================== Pantalla de entrada (rediseño)


def luminancia(hex_):
    def canal(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(a, b):
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_la_contrasena_trae_su_boton_ver_adentro_del_campo_y_con_etiqueta(client):
    html = client.get(reverse("cuentas:login")).content.decode()
    assert 'class="campo-clave"' in html
    boton = html.split('data-ver-clave="clave"', 1)[1].split("</button>", 1)[0]
    assert 'aria-pressed="false"' in boton and "Ver u ocultar la contraseña" in boton
    assert "<span>Ver</span>" in boton  # palabra visible, no solo un ícono


def test_la_entrada_muestra_las_ventajas_y_el_pie_sin_romper_los_textos_conocidos(client):
    html = client.get(reverse("cuentas:login")).content.decode()
    for texto in (
        "Soy alumno",
        "Soy profesor",
        "Tu DNI",
        "Tu contraseña",
        "Crea tu contraseña aquí",
        "Todos los derechos reservados",
    ):
        assert texto in html, texto
    assert html.count("publica-centro") == 1 and html.count('class="publica-pie"') == 1
    assert "Tu correo del aula" in client.get(reverse("cuentas:login") + "?como=personal").content.decode()


def test_los_textos_de_ejemplo_de_los_campos_se_leen_bien():
    """El número de ejemplo (12345678) es una pista: debe tener contraste 4.5:1 en claro y en oscuro."""
    css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
    claro = re.search(r"\.campo-grande::placeholder \{ color: (#[0-9A-Fa-f]{6})", css).group(1)
    oscuro = re.search(r"\.form-control::placeholder \{ color: (#[0-9A-Fa-f]{6})", css).group(1)
    assert contraste(claro, "#FFFFFF") >= 4.5, f"ejemplo en modo claro: {contraste(claro, '#FFFFFF'):.2f}"
    assert contraste(oscuro, "#15203A") >= 4.5, f"ejemplo en modo oscuro: {contraste(oscuro, '#15203A'):.2f}"


def test_en_celular_el_boton_de_modo_tiene_su_propia_fila_y_no_tapa_el_nombre_del_cetpro():
    css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
    final = css[css.index("Pantalla de entrada (rediseño)") :]
    celular = final.split("@media (max-width: 991.98px) {", 1)[1].split("\n}", 1)[0]
    assert "padding-top: 4.25rem" in celular and ".publica-marca { padding-right: 0; }" in celular
