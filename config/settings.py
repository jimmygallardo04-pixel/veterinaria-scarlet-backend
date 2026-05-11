"""
Django settings — Veterinaria Scarlet backend.

Todas las variables sensibles se leen desde el entorno (.env en desarrollo,
variables de entorno reales en producción). Nunca hardcodear secretos aquí.
"""

import logging
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _split_env_list(var_name: str, default: str = "") -> list[str]:
    raw_value = os.getenv(var_name, default) or ""
    values: list[str] = []
    for part in raw_value.split(","):
        candidate = part.strip()
        if not candidate or candidate == ".":
            continue
        values.append(candidate)
    return values


def _normalize_csrf_trusted_origins(origins: list[str]) -> list[str]:
    normalized: list[str] = []
    for origin in origins:
        if "://" in origin:
            normalized.append(origin)
            continue
        # Django exige esquema (http/https). En local suele ser http; en prod https.
        scheme = "http://" if origin.startswith(("localhost", "127.0.0.1", "0.0.0.0")) else "https://"
        normalized.append(f"{scheme}{origin}")
    return normalized


# ─── Rutas ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Seguridad ────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-build-key")
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
ALLOWED_HOSTS = _split_env_list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = _normalize_csrf_trusted_origins(_split_env_list("CSRF_TRUSTED_ORIGINS"))

# Clave secreta requerida para crear nuevas clínicas vía /api/v1/registro/.
# Si no está configurada, el endpoint de registro queda deshabilitado.
REGISTRO_SECRET_KEY = os.getenv("REGISTRO_SECRET_KEY", "")

# ── Email / Resend ─────────────────────────────────────────────────────────────
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@veterinariascarlet.cl")

# Render y otros proxies envían este header para indicar HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ─── Seguridad en producción ──────────────────────────────────────────────────
# En producción (DEBUG=False) se activan todas las cabeceras de seguridad.
# En desarrollo se desactivan para no requerir HTTPS local.

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31_536_000          # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
else:
    logger.warning(
        "⚠️  DEBUG=True — las cabeceras de seguridad HTTPS están desactivadas. "
        "No usar esta configuración en producción."
    )

# ─── Aplicaciones ─────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    # Propias
    "clinic",
]

# ─── Middleware ───────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ─── URLs y WSGI ──────────────────────────────────────────────────────────────

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# ─── Templates ────────────────────────────────────────────────────────────────

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ─── Base de datos ────────────────────────────────────────────────────────────

DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=not DEBUG,  # SSL solo en producción; en dev puede no estar disponible
    )
}

# ─── Caché ────────────────────────────────────────────────────────────────────
# En producción se puede cambiar a Redis configurando CACHE_URL en el entorno.
# Ejemplo: CACHE_URL=redis://localhost:6379/1
#
# Los catálogos (Especie, SexoPaciente, TipoArchivoDocumento) usan caché con
# timeout de 5 minutos para reducir queries repetitivas.

_cache_url = os.getenv("CACHE_URL", "")

if _cache_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _cache_url,
            "TIMEOUT": 300,  # 5 minutos por defecto
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        }
    }
else:
    # LocMemCache es suficiente para un solo proceso (desarrollo / Render free tier)
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "veterinaria-scarlet",
            "TIMEOUT": 300,
        }
    }

CACHE_TIMEOUT_CATALOGOS = 300   # 5 min — catálogos casi estáticos
CACHE_TIMEOUT_ALERTAS = 60      # 1 min — alertas clínicas

# ─── Validación de contraseñas ────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── Internacionalización ─────────────────────────────────────────────────────

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = False  # El backend almacena fechas sin timezone (naive datetimes)

# ─── Archivos estáticos ───────────────────────────────────────────────────────

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ─── Primary key ──────────────────────────────────────────────────────────────

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Django REST Framework ────────────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PAGINATION_CLASS": "clinic.pagination.ClinicPagination",
    "PAGE_SIZE": 20,
    # Rate limiting global. Los endpoints de login/registro tienen throttles propios.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/min",
        "user": "200/min",
        "login": "5/min",
        "registro": "10/hour",
        "validacion_codigo": "5/hour",
    },
    # Handler global de excepciones con respuestas estructuradas
    "EXCEPTION_HANDLER": "clinic.exceptions.custom_exception_handler",
    # Esquema OpenAPI generado por drf-spectacular
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# ─── JWT ──────────────────────────────────────────────────────────────────────

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),   # reducido de 12h a 1h
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ─── CORS ─────────────────────────────────────────────────────────────────────

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = _split_env_list("CORS_ALLOWED_ORIGINS", default="http://localhost:3000")

# ─── OpenAPI / Swagger (drf-spectacular) ──────────────────────────────────────

SPECTACULAR_SETTINGS = {
    "TITLE": "Veterinaria Scarlet API",
    "DESCRIPTION": (
        "API REST para la gestión de clínicas veterinarias. "
        "Permite administrar tutores, pacientes, fichas clínicas, citas, "
        "vacunas, tratamientos y documentos."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CONTACT": {"name": "Equipo Veterinaria Scarlet"},
    "LICENSE": {"name": "Privado"},
    "SCHEMA_PATH_PREFIX": r"/api/v1/",
}

# ─── Logging estructurado ─────────────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        # Lógica de negocio propia — INFO en producción, DEBUG en desarrollo
        "clinic": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        # Queries SQL — solo en DEBUG para no saturar logs de producción
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "WARNING",
            "propagate": False,
        },
        # Errores de Django y DRF siempre visibles
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
