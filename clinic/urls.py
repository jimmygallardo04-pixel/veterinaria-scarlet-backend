from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    TutorViewSet,
    PacienteViewSet,
    FichaClinicaViewSet,
    CitaViewSet,
    VacunaViewSet,
    TratamientoViewSet,
    ArchivoDocumentoViewSet,
    EspecieViewSet,
    SexoPacienteViewSet,
    TipoArchivoDocumentoViewSet,
    AlertaClinicaViewSet,
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
]