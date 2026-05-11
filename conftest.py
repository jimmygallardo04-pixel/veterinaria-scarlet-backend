"""
Configuración global de pytest para el backend de Veterinaria Scarlet.

La configuración de base de datos (SQLite en memoria) y la desactivación
de throttles viven en config/test_settings.py, apuntado por pytest.ini
mediante DJANGO_SETTINGS_MODULE = config.test_settings.

Este archivo existe para documentar esa decisión y puede usarse para
definir fixtures globales en el futuro.

Cómo correr los tests
---------------------
    # Todos los tests
    pytest

    # Con cobertura
    pytest --cov=clinic --cov-report=term-missing

    # Un módulo específico
    pytest clinic/tests/test_models.py -v

    # Un test específico
    pytest clinic/tests/test_services.py::RegistrarClinicaTest::test_email_duplicado_lanza_error -v
"""
