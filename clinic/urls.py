"""
URLs del módulo clinic — montadas bajo /api/v1/ por config/urls.py.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AlertaClinicaViewSet,
    ArchivoDocumentoViewSet,
    CitaViewSet,
    EspecieViewSet,
    FichaClinicaViewSet,
    PacienteViewSet,
    SexoPacienteViewSet,
    TipoArchivoDocumentoViewSet,
    TratamientoViewSet,
    TutorViewSet,
    VacunaViewSet,
    solicitar_codigo_view,
    validar_codigo_view,
    veterinario_detail_view,
    veterinarios_view,
)

router = DefaultRouter()
router.register(r"tutores", TutorViewSet, basename="tutores")
router.register(r"pacientes", PacienteViewSet, basename="pacientes")
router.register(r"fichas", FichaClinicaViewSet, basename="fichas")
router.register(r"citas", CitaViewSet, basename="citas")
router.register(r"vacunas", VacunaViewSet, basename="vacunas")
router.register(r"tratamientos", TratamientoViewSet, basename="tratamientos")
router.register(r"archivos", ArchivoDocumentoViewSet, basename="archivos")
router.register(r"especies", EspecieViewSet, basename="especies")
router.register(r"sexos", SexoPacienteViewSet, basename="sexos")
router.register(r"tipos-archivo", TipoArchivoDocumentoViewSet, basename="tipos-archivo")
router.register(r"alertas", AlertaClinicaViewSet, basename="alertas")

urlpatterns = [
    path("", include(router.urls)),
    path("veterinarios/", veterinarios_view, name="veterinarios"),
    path("veterinarios/<int:pk>/", veterinario_detail_view, name="veterinario-detail"),
    path("verificar-email/solicitar/", solicitar_codigo_view, name="solicitar-codigo"),
    path("verificar-email/validar/", validar_codigo_view, name="validar-codigo"),
]
