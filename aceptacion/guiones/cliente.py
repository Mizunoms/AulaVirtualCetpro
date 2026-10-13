import http.cookiejar
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib

import os

BASE = os.environ.get("BASE", "http://127.0.0.1:8090")
fallos = []


ULTIMO = ["", ""]


def ok(cond, msg):
    print(("  OK  " if cond else "  FALLA ") + msg)
    if not cond:
        fallos.append(msg)
        # Para diagnosticar: guarda la última respuesta que se pidió
        carpeta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".tmp", "fallas")
        os.makedirs(carpeta, exist_ok=True)
        with open(os.path.join(carpeta, "falla-%02d.html" % len(fallos)), "w", encoding="utf-8") as g:
            g.write("<!-- %s | %s -->\n%s" % (msg, ULTIMO[1], ULTIMO[0]))


class Cliente:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.csrf = ""

    def req(self, metodo, ruta, datos=None, archivos=None, seguir=True):
        url = BASE + ruta
        cab = {}
        cuerpo = None
        if archivos is not None:
            b = uuid.uuid4().hex
            partes = []
            for k, v in (datos or {}).items():
                for valor in v if isinstance(v, (list, tuple)) else [v]:
                    partes.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (b, k, valor)).encode())
            for k, (nombre, contenido, tipo) in archivos.items():
                partes.append(
                    (
                        '--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: %s\r\n\r\n'
                        % (b, k, nombre, tipo)
                    ).encode()
                    + contenido
                    + b"\r\n"
                )
            partes.append(("--%s--\r\n" % b).encode())
            cuerpo = b"".join(partes)
            cab["Content-Type"] = "multipart/form-data; boundary=" + b
        elif datos is not None:
            cuerpo = urllib.parse.urlencode(datos, doseq=True).encode()
            cab["Content-Type"] = "application/x-www-form-urlencoded"
        r = urllib.request.Request(url, data=cuerpo, headers=cab, method=metodo)
        op = self.op
        if not seguir:

            class NoRedir(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *a, **k):
                    return None

            op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj), NoRedir)
        try:
            resp = op.open(r)
            codigo, html, hdr = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            codigo, html, hdr = e.code, e.read(), e.headers
        try:
            texto = html.decode("utf-8")
        except UnicodeDecodeError:
            texto = ""
        ULTIMO[0], ULTIMO[1] = texto, metodo + " " + ruta
        m = re.search(r'name="csrfmiddlewaretoken" value="([A-Za-z0-9]+)"', texto)
        if m:
            self.csrf = m.group(1)
        for mal in ("Fatal error", "Warning:", "Notice:", "Deprecated:", "Uncaught", "Parse error"):
            if mal in texto:
                fallos.append('%s %s contiene "%s"' % (metodo, ruta, mal))
                i = texto.index(mal)
                print("  !!! " + re.sub(r"<[^>]+>", "", texto[i : i + 400]))
        return codigo, texto, hdr, html

    def get(self, ruta, **k):
        return self.req("GET", ruta, **k)

    def post(self, ruta, datos=None, archivos=None, **k):
        d = dict(datos or {})
        d.setdefault("csrfmiddlewaretoken", self.csrf)
        return self.req("POST", ruta, d, archivos, **k)

    def login(self, dni, clave):
        self.get("/login")
        return self.post("/login", {"usuario": dni, "clave": clave})


def png():
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 4 for _ in range(4))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def xlsx(hojas):
    """Arma un .xlsx mínimo. hojas = {nombre: {(fila, columna): valor}}, con la fila desde 1 y la columna desde 0 (A = 0).
    Los textos van como str y los números como int o float."""
    import io
    import zipfile
    from xml.sax.saxutils import escape

    def letras(i):
        r = ""
        i += 1
        while i:
            i, m = divmod(i - 1, 26)
            r = chr(65 + m) + r
        return r

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        nombres = list(hojas)
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                % (i + 1)
                for i in range(len(nombres))
            )
            + "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(n), i + 1, i + 1) for i, n in enumerate(nombres))
            + "</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>'
                % (i + 1, i + 1)
                for i in range(len(nombres))
            )
            + "</Relationships>",
        )
        for i, n in enumerate(nombres):
            filas = {}
            for (f, c), v in hojas[n].items():
                filas.setdefault(f, {})[c] = v
            cuerpo = ""
            for f in sorted(filas):
                cuerpo += '<row r="%d">' % f
                for c in sorted(filas[f]):
                    v = filas[f][c]
                    ref = "%s%d" % (letras(c), f)
                    if isinstance(v, (int, float)):
                        cuerpo += '<c r="%s"><v>%s</v></c>' % (ref, v)
                    else:
                        cuerpo += '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, escape(str(v)))
                cuerpo += "</row>"
            z.writestr(
                "xl/worksheets/sheet%d.xml" % (i + 1),
                '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>'
                % cuerpo,
            )
    return buf.getvalue()
