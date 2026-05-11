"""
Test settings — uses SQLite in-memory database to avoid needing
a PostgreSQL connection during testing.
"""
from config.settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Disable password validators for faster test user creation
AUTH_PASSWORD_VALIDATORS = []

# Use a simple secret key for tests
SECRET_KEY = "test-secret-key-not-for-production"

# Disable throttling in tests so Hypothesis can make many requests freely
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # type: ignore[name-defined]  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {},
}

# Disable cache in tests to prevent stale data between test cases.
# DummyCache is a no-op backend: every get() returns None, set() does nothing.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}
