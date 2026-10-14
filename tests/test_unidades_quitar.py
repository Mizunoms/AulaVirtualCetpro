"""Unidades didácticas del módulo: cada fila trae su botón «Quitar» (las de abajo suben) y lo quitado se borra al guardar."""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.academico.models import Modulo, UnidadDidactica

pytestmark = pytest.mark.django_db

JS = (Path(__file__).resolve().parent.parent / "static" / "js" / "app.js").read_text(encoding="utf-8")


@pytest.fixture
def modulo(docente):
    m = Modulo.crear(
        nombre="Soporte – Módulo 1",
        especialidad="Soporte Técnico",
        modulo="Módulo 1",
        periodo="2026-II",
        turno="noche",
        docente=docente,
    )
    UnidadDidactica.guardar_lista(
        m,
        [
            {"nombre": "Organización del área", "creditos": 2, "horas": 40},
            {"nombre": "Atención de incidentes", "creditos": 3, "horas": 60},
            {"nombre": "Redes básicas", "creditos": None, "horas": None},
        ],
    )
    return m


def formulario(docente, **cambios):
    base = {
        "especialidad": "Soporte Técnico",
        "modulo": "Módulo 1",
        "nombre": "",
        "periodo": "2026-II",
        "turno": "tarde",
        "docente_id": str(docente.pk),
    }
    return {**base, **cambios}


def test_cada_fila_trae_su_boton_quitar_con_su_nombre_para_el_lector_de_pantalla(cliente_de, admin):
    html = cliente_de(admin).get(reverse("academico:admin_nuevo")).content.decode()
    maximo = UnidadDidactica.MAX
    assert html.count("data-quitar-unidad") == maximo
    assert 'aria-label="Quitar la unidad 1"' in html and f'aria-label="Quitar la unidad {maximo}"' in html
    assert html.count('type="button" class="btn btn-borde btn-quitar-unidad"') == maximo  # nunca envían el formulario
    assert "Quitar</button>" in html and 'role="status" data-aviso-unidades' in html  # y avisa lo que pasó


def test_el_boton_agregar_otra_unidad_siempre_esta_y_se_esconde_solo_cuando_no_hay_mas(cliente_de, admin, modulo):
    c = cliente_de(admin)
    html = c.get(reverse("academico:admin_editar", args=[modulo.pk])).content.decode()
    boton = re.search(r'<button[^>]*data-mas-filas="lista-unidades"[^>]*>', html).group(0)
    assert "hidden" not in boton  # todavía caben más filas

    UnidadDidactica.guardar_lista(
        modulo, [{"nombre": f"Unidad {i}", "creditos": None, "horas": None} for i in range(UnidadDidactica.MAX)]
    )
    html = c.get(reverse("academico:admin_editar", args=[modulo.pk])).content.decode()
    boton = re.search(r'<button[^>]*data-mas-filas="lista-unidades"[^>]*>', html).group(0)
    assert (
        "hidden" in boton
    )  # con todas las filas llenas no hay más, pero el botón existe: al quitar una, el JavaScript lo vuelve a mostrar


def test_el_formulario_del_docente_tambien_tiene_el_boton(cliente_de, docente):
    html = cliente_de(docente).get(reverse("academico:nuevo")).content.decode()
    assert html.count("data-quitar-unidad") == UnidadDidactica.MAX and "Para sacar una, toca «Quitar»" in html


def test_quitar_una_unidad_y_guardar_la_borra_de_verdad(cliente_de, admin, docente, modulo):
    c = cliente_de(admin)
    nombres = ["Organización del área", "Redes básicas"]  # la del medio se quitó: las de abajo subieron
    r = c.post(
        reverse("academico:admin_actualizar", args=[modulo.pk]),
        formulario(
            docente,
            **{
                "ud_nombre[]": nombres + ["", ""],
                "ud_creditos[]": ["2", "", "", ""],
                "ud_horas[]": ["40", "", "", ""],
                "activo": "1",
            },
        ),
    )
    assert r.status_code == 302
    quedan = list(UnidadDidactica.objects.filter(modulo=modulo).values_list("nombre", flat=True))
    assert quedan == nombres and "Atención de incidentes" not in quedan


def test_quitarlas_todas_deja_el_modulo_sin_unidades(cliente_de, admin, docente, modulo):
    cliente_de(admin).post(
        reverse("academico:admin_actualizar", args=[modulo.pk]),
        formulario(
            docente, **{"ud_nombre[]": ["", "", ""], "ud_creditos[]": ["", "", ""], "ud_horas[]": ["", "", ""], "activo": "1"}
        ),
    )
    assert not UnidadDidactica.objects.filter(modulo=modulo).exists()


def test_el_javascript_de_quitar_sube_las_de_abajo_deja_tres_filas_y_avisa():
    bloque = JS[JS.index("Unidades didácticas: «Quitar» saca la unidad") : JS.index("Menús «Más» y «Opciones»")]
    assert "listaUnidades.addEventListener('click'" in bloque and "closest('[data-quitar-unidad]')" in bloque
    assert "campo.value = desde[j].value" in bloque  # las de abajo suben un lugar
    assert "if (quedan > 3) { ultima.hidden = true;" in bloque  # siempre quedan al menos 3 filas
    assert "masUnidades.hidden = false" in bloque  # vuelve a caber «Agregar otra unidad»
    assert "Unidad quitada. Quedan" in bloque and ".focus()" in bloque  # avisa y deja el cursor en un lugar lógico


def test_el_boton_quitar_es_grande_y_en_celular_cabe_junto_a_creditos_y_horas():
    css = (Path(__file__).resolve().parent.parent / "static" / "css" / "app.css").read_text(encoding="utf-8")
    regla = re.search(r"\.fila-unidad \.btn-quitar-unidad \{([^}]*)\}", css).group(1)
    assert int(re.search(r"min-height: (\d+)px", regla).group(1)) >= 44  # blanco táctil mínimo
    celular = css.split("@media (max-width: 420px) { /* en celular, créditos, horas y «Quitar» caben en una sola línea */", 1)[
        1
    ].split("\n}", 1)[0]
    assert ".fila-unidad .campo-num { width: 96px; }" in celular
