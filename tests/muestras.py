"""Archivos de muestra para las pruebas (contenido real mínimo, para que pasen la revisión del tipo de archivo)."""

import base64

from django.core.files.uploadedfile import SimpleUploadedFile

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def png(nombre="foto.png"):
    return SimpleUploadedFile(nombre, PNG, content_type="image/png")


def pdf(nombre="guia.pdf"):
    return SimpleUploadedFile(nombre, PDF, content_type="application/pdf")
