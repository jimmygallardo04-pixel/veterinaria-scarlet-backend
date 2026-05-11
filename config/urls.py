"""
URL configuration — Veterinaria Scarlet backend.

Estructura:
    /admin/              → Panel de administración de Django
    /api/v1/             → API REST versionada (v1)
    /api/v1/login/       → Obtener tokens JWT
    /api/v1/refresh/     → Renovar access token
    /api/v1/me/          → Usuario autenticado
    /api/v1/registro/    → Registro de nueva clínica
    /api/schema/         → Esquema OpenAPI (JSON/YAML)
    /api/docs/           → Swagger UI
    /api/redoc/          → ReDoc UI

Versionado:
    La versión actual es v1. Cuando se introduzcan cambios breaking,
    se añadirá /api/v2/ manteniendo /api/v1/ activo durante la transición.
"""

from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework_simplejwt.views import TokenRefreshView

from clinic.views import ThrottledTokenObtainPairView, clinica_view, me_view, registro_clinica_view

# ─── API v1 ───────────────────────────────────────────────────────────────────

api_v1_patterns = [
    path("", include("clinic.urls")),
    path("login/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", me_view, name="me"),
    path("registro/", registro_clinica_view, name="registro_clinica"),
    path("clinica/", clinica_view, name="clinica"),
]

urlpatterns = [
    path("admin/", admin.site.urls),

    # API versionada
    path("api/v1/", include((api_v1_patterns, "v1"))),

    # Documentación OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
