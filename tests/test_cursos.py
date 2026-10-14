"""Cursos (programas de estudios): «Nuevo curso», la página del curso con sus módulos, editar y eliminar."""

import re

import pytest
from django.urls import reverse

from apps.academico import cursos
from apps.academico.models import Modulo
from apps.nucleo import ajustes, archivos, color
from apps.nucleo.contexto import foto_especialidad
from apps.nucleo.models import Registro

from . import muestras

pytestmark = pytest.mark.django_db


@pytest.fixture
def modulo(docente):
    return Modulo.crear(
        nombre="Soporte – Módulo 1",
        especialidad="Soporte Técnico",
        modulo="Módulo 1",
        periodo="2026-II",
        turno="noche",
        docente=docente,
    )


def nombres():
    return [e["nombre"] for e in ajustes.especialidades()]


def crear(c, nombre="Electricidad", color_hex="#166534", **extra):
    return c.post(reverse("academico:admin_curso_nuevo"), {"nombre": nombre, "color": color_hex, **extra})


def texto_de(c, respuesta):
    return c.get(respuesta["Location"]).content.decode()


# ===================================================================== La lógica


def test_las_muestras_de_color_se_leen_con_letra_blanca():
    assert len(cursos.COLORES_SUGERIDOS) >= 8
    for hexa, nombre in cursos.COLORES_SUGERIDOS:
        assert color.valido(hexa) and nombre
        assert color.contraste(hexa, "#FFFFFF") >= 4.5, (hexa, nombre)
    assert cursos.COLOR_NUEVO in [h for h, _ in cursos.COLORES_SUGERIDOS]


def test_el_nombre_se_limpia_y_no_se_repite_sin_mirar_mayusculas_ni_tildes():
    assert cursos.revisar_nombre("  Electricidad   Industrial  ") == "Electricidad Industrial"
    assert len(cursos.revisar_nombre("x" * 300)) == 100
    for malo in ("", "   ", "¡¡¡", "Nuevo"):
        with pytest.raises(cursos.CursoError):
            cursos.revisar_nombre(malo)
    for repetido in ("Soporte Técnico", "soporte tecnico", "SOPORTE   TÉCNICO"):
        with pytest.raises(cursos.CursoError, match="Ya hay un curso llamado «Soporte Técnico»"):
            cursos.revisar_nombre(repetido)
    assert (
        cursos.revisar_nombre("Soporte Técnico", excepto="soporte-tecnico") == "Soporte Técnico"
    )  # el propio nombre vale al editar


def test_el_color_debe_ser_valido_y_oscuro():
    assert cursos.revisar_color(" #166534 ") == "#166534"
    for malo in ("", "verde", "#12", "#GGGGGG", "#FFFF00", "#FFFFFF"):
        with pytest.raises(cursos.CursoError):
            cursos.revisar_color(malo)


def test_cada_curso_se_encuentra_por_su_slug():
    c = cursos.buscar("soporte-tecnico")
    assert c["nombre"] == "Soporte Técnico" and c["slug"] == "soporte-tecnico"
    assert cursos.buscar("panaderia-y-pasteleria")["nombre"] == "Panadería y Pastelería"
    assert cursos.buscar("no-existe") is None


# ===================================================================== La pantalla Cursos


def test_cursos_tiene_nuevo_curso_y_cada_curso_se_abre(cliente_de, admin, modulo):
    c = cliente_de(admin)
    html = c.get(reverse("academico:admin_cursos")).content.decode()
    assert "Nuevo curso" in html and reverse("academico:admin_curso_nuevo") in html
    assert "Abrir curso" in html and reverse("academico:admin_curso", args=["soporte-tecnico"]) in html
    assert "Agregar módulo" in html and "Primero se crea el curso y dentro se agregan sus" in html
    assert "Agregar o cambiar cursos" not in html  # ya no hace falta ir a Ajustes


def test_solo_el_administrador_maneja_cursos(client, cliente_de, docente, alumno, modulo):
    direcciones = [
        reverse("academico:admin_curso_nuevo"),
        reverse("academico:admin_curso", args=["soporte-tecnico"]),
        reverse("academico:admin_curso_editar", args=["soporte-tecnico"]),
        reverse("academico:admin_curso_eliminar", args=["soporte-tecnico"]),
    ]
    for url in direcciones:
        assert client.get(url).status_code == 302  # sin sesión: a entrar
        for persona in (docente, alumno):
            c = cliente_de(persona)
            assert c.get(url).status_code == 403, url
            assert c.post(url, {"nombre": "Hackeado", "color": "#166534"}).status_code == 403, url
    assert "Hackeado" not in nombres()


# ===================================================================== Crear


def test_el_formulario_de_curso_trae_nombre_color_y_foto(cliente_de, admin):
    html = cliente_de(admin).get(reverse("academico:admin_curso_nuevo")).content.decode()
    assert "Nombre del curso" in html and 'name="nombre"' in html and "Crear curso" in html
    assert html.count("data-poner-color") == len(cursos.COLORES_SUGERIDOS)
    assert 'type="color"' in html and 'name="color"' in html and 'type="file"' in html and 'name="foto"' in html
    assert re.search(r'aria-label="Azul"', html)  # cada muestra tiene nombre para quien no ve el color
    assert 'enctype="multipart/form-data"' in html and "csrfmiddlewaretoken" in html


def test_crear_un_curso_lleva_a_su_pagina_para_agregar_los_modulos(cliente_de, admin):
    c = cliente_de(admin)
    r = crear(c)
    assert r.status_code == 302 and r["Location"] == reverse("academico:admin_curso", args=["electricidad"])
    assert "Electricidad" in nombres()
    assert next(e for e in ajustes.especialidades() if e["nombre"] == "Electricidad")["color"] == "#166534"
    html = texto_de(c, r)
    assert "Curso «Electricidad» creado. Ahora agrega su primer módulo." in html
    assert "Este curso todavía no tiene módulos" in html and "Crear Módulo 1" in html and "Crear Módulo 2" in html
    assert "especialidad=Electricidad&amp;modulo=M%C3%B3dulo%201" in html
    assert Registro.objects.filter(accion="ajustes", detalle__contains="creó el curso «Electricidad»").exists()


def test_los_cursos_de_siempre_se_conservan_al_crear_uno_nuevo(cliente_de, admin):
    antes = nombres()
    crear(cliente_de(admin))
    assert nombres() == [*antes, "Electricidad"]


def test_crear_con_foto_la_guarda_y_la_foto_se_ve_en_el_curso(cliente_de, admin):
    c = cliente_de(admin)
    r = crear(c, foto=muestras.png("taller.png"))
    curso = next(e for e in ajustes.especialidades() if e["nombre"] == "Electricidad")
    assert curso["foto"].endswith(".png") and archivos.es_imagen(curso["foto"])
    assert "n=Electricidad" in foto_especialidad("Electricidad")
    assert "n=Electricidad" in texto_de(c, r)  # la página del curso usa la foto de fondo


@pytest.mark.parametrize(
    "datos,mensaje",
    [
        ({"nombre": ""}, "Escribe el nombre del curso"),
        ({"nombre": "soporte tecnico"}, "Ya hay un curso llamado «Soporte Técnico»"),
        ({"nombre": "Nuevo"}, "Ese nombre no se puede usar"),
        ({"color": "#FFFF00"}, "Ese color es muy claro"),
        ({"color": "rojo"}, "Elige un color para el curso"),
    ],
)
def test_crear_con_errores_vuelve_al_formulario_sin_guardar_nada(cliente_de, admin, datos, mensaje):
    c = cliente_de(admin)
    antes = nombres()
    r = c.post(reverse("academico:admin_curso_nuevo"), {"nombre": "Electricidad", "color": "#166534", **datos})
    assert r["Location"] == reverse("academico:admin_curso_nuevo")
    assert mensaje in texto_de(c, r)
    assert nombres() == antes


def test_un_envio_con_error_no_deja_la_foto_ni_el_curso(cliente_de, admin, tmp_path):
    c = cliente_de(admin)
    antes = nombres()
    r = c.post(reverse("academico:admin_curso_nuevo"), {"nombre": "Soporte Técnico", "color": "#166534", "foto": muestras.png()})
    assert "Ya hay un curso" in texto_de(c, r) and nombres() == antes
    subidas = tmp_path / "uploads"
    assert not subidas.exists() or not any(p.is_file() for p in subidas.rglob("*"))  # no quedó ninguna foto suelta


def test_una_foto_que_no_es_imagen_no_vale(cliente_de, admin):
    c = cliente_de(admin)
    antes = nombres()
    r = c.post(reverse("academico:admin_curso_nuevo"), {"nombre": "Electricidad", "color": "#166534", "foto": muestras.pdf()})
    assert "Sube una foto JPG, PNG o WEBP" in texto_de(c, r) and nombres() == antes


def test_lo_escrito_se_recuerda_cuando_vuelve_con_error(cliente_de, admin):
    c = cliente_de(admin)
    r = c.post(reverse("academico:admin_curso_nuevo"), {"nombre": "Electricidad Industrial", "color": "#FFFF00"})
    html = texto_de(c, r)
    assert 'value="Electricidad Industrial"' in html and "#ffff00" in html.lower()


def test_el_nombre_nuevo_no_choca_con_las_direcciones_del_aula(cliente_de, admin):
    c = cliente_de(admin)
    assert c.get("/admin/cursos/nuevo").status_code == 200  # sigue siendo el formulario, no un curso llamado «nuevo»
    crear(c, "Nuevo")
    assert "Nuevo" not in nombres()


# ===================================================================== La página del curso


def test_la_pagina_del_curso_muestra_sus_modulos_y_los_botones(cliente_de, admin, modulo):
    c = cliente_de(admin)
    html = c.get(reverse("academico:admin_curso", args=["soporte-tecnico"])).content.decode()
    assert "Módulos de este curso" in html and "Soporte – Módulo 1" in html and "Prof. María Torres" in html
    assert "1 módulo" in html and "Agregar módulo" in html and "Editar curso" in html and "Cargar plan de estudios" in html
    assert reverse("academico:modulo", args=[modulo.pk]) in html and reverse("academico:admin_alumnos", args=[modulo.pk]) in html
    assert "especialidad=Soporte%20T%C3%A9cnico" in html
    assert "Este curso todavía no tiene módulos" not in html


def test_otro_curso_no_muestra_los_modulos_de_este(cliente_de, admin, modulo):
    html = cliente_de(admin).get(reverse("academico:admin_curso", args=["soldadura-universal"])).content.decode()
    assert "Soporte – Módulo 1" not in html and "Este curso todavía no tiene módulos" in html


def test_los_modulos_archivados_se_cuentan_aparte(cliente_de, admin, modulo, docente):
    Modulo.crear(nombre="Viejo", especialidad="Soporte Técnico", periodo="2025-II", turno="tarde", docente=docente, activo=False)
    html = cliente_de(admin).get(reverse("academico:admin_curso", args=["soporte-tecnico"])).content.decode()
    assert "1 módulo archivado" in html and "estado=archivados" in html and ">Viejo<" not in html


def test_un_curso_que_no_existe_da_pagina_no_encontrada(cliente_de, admin):
    c = cliente_de(admin)
    for nombre in ("admin_curso", "admin_curso_editar", "admin_curso_eliminar"):
        assert c.get(reverse(f"academico:{nombre}", args=["no-existe"])).status_code == 404


def test_agregar_modulo_llega_con_el_curso_y_el_modulo_elegidos(cliente_de, admin, docente):
    c = cliente_de(admin)
    url = reverse("academico:admin_nuevo") + "?especialidad=Soldadura%20Universal&modulo=M%C3%B3dulo%202"
    html = c.get(url).content.decode()
    assert re.search(r"<option selected>Soldadura Universal</option>", html)
    assert re.search(r'value="Módulo 2"\s+checked', html) and not re.search(r'value="Módulo 1"\s+checked', html)
    assert f'href="{reverse("academico:admin_curso", args=["soldadura-universal"])}"' in html  # «Volver» regresa al curso
    assert "Nuevo curso" in html  # ¿No está? Créalo con «Nuevo curso»
    assert "Ajustes → Cursos" not in html


def test_un_modulo_inventado_en_la_direccion_no_se_acepta(cliente_de, admin):
    html = cliente_de(admin).get(reverse("academico:admin_nuevo") + "?modulo=Hackeado&especialidad=Nada").content.decode()
    assert 'value="Hackeado"' not in html and re.search(r'value="Módulo 1"\s+checked', html)


def test_se_puede_crear_el_modulo_desde_un_curso_recien_creado(cliente_de, admin, docente):
    c = cliente_de(admin)
    crear(c)
    r = c.post(
        reverse("academico:admin_modulos"),
        {
            "especialidad": "Electricidad",
            "modulo": "Módulo 1",
            "nombre": "",
            "periodo": "2026-II",
            "turno": "tarde",
            "docente_id": str(docente.pk),
        },
    )
    assert r.status_code == 302
    m = Modulo.objects.get(especialidad="Electricidad")
    assert m.nombre == "Electricidad – Módulo 1" and m.codigo.startswith("ELE")
    html = c.get(reverse("academico:admin_curso", args=["electricidad"])).content.decode()
    assert "Electricidad – Módulo 1" in html and "Este curso todavía no tiene módulos" not in html


# ===================================================================== Editar


def test_el_formulario_de_editar_trae_lo_guardado(cliente_de, admin):
    c = cliente_de(admin)
    crear(c, foto=muestras.png())
    html = c.get(reverse("academico:admin_curso_editar", args=["electricidad"])).content.decode()
    assert 'value="Electricidad"' in html and 'value="#166534"' in html and "Guardar cambios" in html
    assert "Quitar la foto" in html and "Foto actual del curso" in html
    assert "Si lo cambias, se cambia también en sus módulos" in html


def test_cambiar_el_nombre_lo_cambia_tambien_en_sus_modulos(cliente_de, admin, modulo):
    c = cliente_de(admin)
    r = c.post(
        reverse("academico:admin_curso_editar", args=["soporte-tecnico"]), {"nombre": "Soporte y Redes", "color": "#0E7490"}
    )
    assert r["Location"] == reverse("academico:admin_curso", args=["soporte-y-redes"])  # su dirección sigue al nombre
    modulo.refresh_from_db()
    assert modulo.especialidad == "Soporte y Redes"
    assert "Soporte Técnico" not in nombres() and "Soporte y Redes" in nombres()
    assert ajustes.color_curso("Soporte y Redes") == "#0E7490"
    html = texto_de(c, r)  # el mensaje se muestra una sola vez
    assert "Soporte – Módulo 1" in html and "Cambios guardados." in html
    assert Registro.objects.filter(
        accion="ajustes", detalle__contains="«Soporte Técnico» (ahora se llama «Soporte y Redes»)"
    ).exists()


def test_cambiar_solo_el_color_no_toca_el_nombre_ni_los_modulos(cliente_de, admin, modulo):
    c = cliente_de(admin)
    r = c.post(
        reverse("academico:admin_curso_editar", args=["soporte-tecnico"]), {"nombre": "Soporte Técnico", "color": "#7E22CE"}
    )
    assert r["Location"] == reverse("academico:admin_curso", args=["soporte-tecnico"])
    modulo.refresh_from_db()
    assert modulo.especialidad == "Soporte Técnico" and ajustes.color_curso("Soporte Técnico") == "#7E22CE"


def test_no_se_puede_cambiar_a_un_nombre_que_ya_existe_ni_a_un_color_claro(cliente_de, admin, modulo):
    c = cliente_de(admin)
    url = reverse("academico:admin_curso_editar", args=["soporte-tecnico"])
    r = c.post(url, {"nombre": "soldadura universal", "color": "#1249A3"})
    assert r["Location"] == url and "Ya hay un curso llamado «Soldadura Universal»" in texto_de(c, r)
    r = c.post(url, {"nombre": "Soporte Técnico", "color": "#FFFF00"})
    assert "Ese color es muy claro" in texto_de(c, r)
    modulo.refresh_from_db()
    assert modulo.especialidad == "Soporte Técnico" and ajustes.color_curso("Soporte Técnico") == "#1249A3"


def test_la_foto_se_conserva_al_renombrar_se_cambia_y_se_quita(cliente_de, admin):
    c = cliente_de(admin)
    crear(c, foto=muestras.png("uno.png"))
    primera = next(e for e in ajustes.especialidades() if e["nombre"] == "Electricidad")["foto"]
    url = reverse("academico:admin_curso_editar", args=["electricidad"])
    c.post(url, {"nombre": "Electricidad Industrial", "color": "#166534"})
    assert next(e for e in ajustes.especialidades() if e["nombre"] == "Electricidad Industrial")["foto"] == primera  # se conserva

    url = reverse("academico:admin_curso_editar", args=["electricidad-industrial"])
    c.post(url, {"nombre": "Electricidad Industrial", "color": "#166534", "foto": muestras.png("dos.png")})
    segunda = next(e for e in ajustes.especialidades() if e["nombre"] == "Electricidad Industrial")["foto"]
    assert segunda != primera
    assert archivos._real(segunda) is not None and archivos._real(primera) is None  # la vieja se borró del disco

    c.post(url, {"nombre": "Electricidad Industrial", "color": "#166534", "quitar_foto": "1"})
    assert not next(e for e in ajustes.especialidades() if e["nombre"] == "Electricidad Industrial").get("foto")
    assert archivos._real(segunda) is None


# ===================================================================== Eliminar (de verdad)


def test_eliminar_un_curso_sin_modulos_pide_confirmar_y_lo_borra_de_verdad(cliente_de, admin):
    c = cliente_de(admin)
    crear(c, foto=muestras.png())
    foto = next(e for e in ajustes.especialidades() if e["nombre"] == "Electricidad")["foto"]
    url = reverse("academico:admin_curso_eliminar", args=["electricidad"])
    html = c.get(url).content.decode()
    assert "¿Eliminar el curso «Electricidad»?" in html and "Sí, eliminar el curso" in html and "y su foto" in html
    assert "Electricidad" in nombres()  # mirar la pantalla no borra nada
    r = c.post(url)
    assert r["Location"] == reverse("academico:admin_cursos")
    assert "Electricidad" not in nombres()
    assert archivos._real(foto) is None  # la foto también se borró
    assert "Curso eliminado: «Electricidad»." in texto_de(c, r)
    assert Registro.objects.filter(accion="ajustes", detalle__contains="eliminó el curso «Electricidad»").exists()
    assert c.get(reverse("academico:admin_curso", args=["electricidad"])).status_code == 404


def test_un_curso_con_modulos_no_se_elimina_y_dice_cuales_hay_que_eliminar_primero(cliente_de, admin, modulo, docente):
    Modulo.crear(nombre="Viejo", especialidad="Soporte Técnico", periodo="2025-II", turno="tarde", docente=docente, activo=False)
    c = cliente_de(admin)
    url = reverse("academico:admin_curso_eliminar", args=["soporte-tecnico"])
    html = c.get(url).content.decode()
    assert "Todavía no se puede eliminar" in html and "Tiene 2 módulos" in html
    assert "Sí, eliminar el curso" not in html
    assert reverse("academico:admin_eliminar", args=[modulo.pk]) in html and "(archivado)" in html
    r = c.post(url)  # aunque se fuerce el envío
    assert r["Location"] == url and "Tiene 2 módulos" in texto_de(c, r)
    assert "Soporte Técnico" in nombres() and Modulo.objects.count() == 2


def test_cuando_se_eliminan_sus_modulos_el_curso_ya_se_puede_eliminar(cliente_de, admin, modulo):
    c = cliente_de(admin)
    assert "Primero elimina esos módulos" in c.get(reverse("academico:admin_curso", args=["soporte-tecnico"])).content.decode()
    c.post(reverse("academico:admin_eliminar", args=[modulo.pk]), {"entiendo": "1"})
    assert "Como no tiene módulos" in c.get(reverse("academico:admin_curso", args=["soporte-tecnico"])).content.decode()
    c.post(reverse("academico:admin_curso_eliminar", args=["soporte-tecnico"]))
    assert "Soporte Técnico" not in nombres()


def test_siempre_debe_quedar_al_menos_un_curso(cliente_de, admin):
    ajustes.guardar_especialidades([{"nombre": "Único", "color": "#1249A3"}])
    c = cliente_de(admin)
    url = reverse("academico:admin_curso_eliminar", args=["unico"])
    assert "Debe quedar al menos un curso" in c.get(url).content.decode()
    r = c.post(url)
    assert "Debe quedar al menos un curso" in texto_de(c, r) and nombres() == ["Único"]


# ===================================================================== Lo que ya existía sigue igual


def test_la_pestana_cursos_de_ajustes_sigue_funcionando_y_apunta_a_la_pantalla_nueva(cliente_de, admin, modulo):
    html = cliente_de(admin).get(reverse("nucleo:ajustes") + "?tab=especialidades").content.decode()
    assert "Cursos (programas de estudios)" in html and "Guardar cursos" in html
    assert reverse("academico:admin_cursos") in html and "Nuevo curso" in html


def test_un_curso_creado_aqui_aparece_en_ajustes_y_al_reves(cliente_de, admin):
    c = cliente_de(admin)
    crear(c)
    assert "Electricidad" in c.get(reverse("nucleo:ajustes") + "?tab=especialidades").content.decode()
    datos = {}
    n = len(ajustes.especialidades())
    for i, e in enumerate(ajustes.especialidades()):
        datos |= {f"nombre[{i}]": e["nombre"], f"original[{i}]": e["nombre"], f"color[{i}]": e["color"]}
    datos |= {f"nombre[{n}]": "Cocina", f"original[{n}]": "", f"color[{n}]": "#9A3412"}
    c.post(reverse("nucleo:ajustes_especialidades"), datos)
    assert c.get(reverse("academico:admin_curso", args=["cocina"])).status_code == 200


def test_el_docente_sigue_viendo_el_curso_nuevo_al_crear_su_modulo(cliente_de, admin, docente):
    crear(cliente_de(admin))
    html = cliente_de(docente).get(reverse("academico:nuevo")).content.decode()
    assert "Electricidad" in html
