"""
Configuración global de pytest para el backend de Veterinaria Scarlet.

La configuración de base de datos (SQLite en memoria) y la desactivación
de throttles viven en config/test_settings.py, apuntado por pytest.ini
mediante DJANGO_SETTINGS_MODULE = config.test_settings.

Fixtures globales
-----------------
Las fixtures definidas aquí están disponibles en todos los archivos de test
sin necesidad de importarlas. Usan `django_db` implícitamente a través de
los tests que las consumen.

Cómo correr los tests
---------------------
    # Todos los tests
    pytest

    # Con cobertura
    pytest --cov=clinic --cov-report=term-missing --cov-fail-under=70

    # Un módulo específico
    pytest clinic/tests/test_models.py -v

    # Un test específico
    pytest clinic/tests/test_services.py::RegistrarClinicaTest::test_email_duplicado_lanza_error -v
"""

import pytest
from rest_framework.test import APIClient

from clinic.models import Clinica, PerfilUsuario
from clinic.tests.helpers import make_clinica, make_user


@pytest.fixture
def api_client():
    """APIClient sin autenticar."""
    return APIClient()


@pytest.fixture
def clinica(db):
    """Clínica de prueba reutilizable."""
    return make_clinica("Clínica Fixture")


@pytest.fixture
def admin_user(db, clinica):
    """Usuario con rol admin asociado a `clinica`."""
    return make_user(username="admin_fixture", clinica=clinica)


@pytest.fixture
def vet_user(db, clinica):
    """Usuario con rol veterinario asociado a `clinica`."""
    from django.contrib.auth.models import User
    user = User.objects.create_user(
        username="vet_fixture",
        email="vet_fixture@test.cl",
        password="testpass123",
        first_name="Vet Fixture",
    )
    PerfilUsuario.objects.create(
        user=user,
        clinica=clinica,
        rol=PerfilUsuario.Rol.VETERINARIO,
    )
    return user


@pytest.fixture
def admin_client(api_client, admin_user):
    """APIClient autenticado como admin."""
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def vet_client(api_client, vet_user):
    """APIClient autenticado como veterinario."""
    api_client.force_authenticate(user=vet_user)
    return api_client
