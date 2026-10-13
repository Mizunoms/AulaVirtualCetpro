import pytest


@pytest.fixture(autouse=True)
def _archivos_estaticos_simples(settings):
    """En las pruebas no hay `collectstatic`: usar el almacenamiento simple evita buscar el manifiesto."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
