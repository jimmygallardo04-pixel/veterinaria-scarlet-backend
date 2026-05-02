from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from datetime import timedelta
from django.utils import timezone
from django.db import models

from .models import (
    Tutor,
    Paciente,
    FichaClinica,
    Cita,
    Vacuna,
    Tratamiento,
    ArchivoDocumento,
    Especie,
    SexoPaciente,
    TipoArchivoDocumento
)

from .serializers import (
    TutorSerializer,
    PacienteSerializer,
    FichaClinicaSerializer,
    FichaClinicaDetalleSerializer,
    CitaSerializer,
    VacunaSerializer,
    TratamientoSerializer,
    ArchivoDocumentoSerializer,
    EspecieSerializer,
    SexoPacienteSerializer,
    TipoArchivoDocumentoSerializer,
)


class SoftDeleteModelViewSet(viewsets.ModelViewSet):
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TutorViewSet(SoftDeleteModelViewSet):
    serializer_class = TutorSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Tutor.objects.filter(
            eliminado_en__isnull=True
        ).order_by("-creado_en")


class EspecieViewSet(SoftDeleteModelViewSet):
    serializer_class = EspecieSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Especie.objects.filter(
            eliminado_en__isnull=True,
            activo=True,
        ).order_by("nombre")


class SexoPacienteViewSet(SoftDeleteModelViewSet):
    serializer_class = SexoPacienteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SexoPaciente.objects.filter(
            eliminado_en__isnull=True,
            activo=True,
        ).order_by("nombre")


class PacienteViewSet(SoftDeleteModelViewSet):
    serializer_class = PacienteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Paciente.objects.select_related(
            "tutor",
            "especie",
            "sexo",
        ).filter(
            eliminado_en__isnull=True,
            tutor__eliminado_en__isnull=True,
        ).order_by("-creado_en")


class FichaClinicaViewSet(SoftDeleteModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return FichaClinicaDetalleSerializer
        return FichaClinicaSerializer

    def get_queryset(self):
        queryset = FichaClinica.objects.select_related(
            "paciente",
            "paciente__tutor",
            "paciente__especie",
            "paciente__sexo",
        ).filter(
            eliminado_en__isnull=True,
            paciente__eliminado_en__isnull=True,
            paciente__tutor__eliminado_en__isnull=True,
        )

        paciente_id = self.request.query_params.get("paciente")
        if paciente_id:
            queryset = queryset.filter(paciente_id=paciente_id)

        return queryset.order_by("-fecha")


class CitaViewSet(SoftDeleteModelViewSet):
    serializer_class = CitaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Cita.objects.select_related(
            "paciente",
            "tutor",
        ).filter(
            eliminado_en__isnull=True,
            paciente__eliminado_en__isnull=True,
            tutor__eliminado_en__isnull=True,
        ).order_by("-fecha_hora")


class VacunaViewSet(SoftDeleteModelViewSet):
    serializer_class = VacunaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Vacuna.objects.select_related(
            "paciente",
        ).filter(
            eliminado_en__isnull=True,
            paciente__eliminado_en__isnull=True,
        )

        paciente_id = self.request.query_params.get("paciente")
        if paciente_id:
            queryset = queryset.filter(paciente_id=paciente_id)

        return queryset.order_by("-fecha_aplicacion")


class TratamientoViewSet(SoftDeleteModelViewSet):
    serializer_class = TratamientoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Tratamiento.objects.select_related(
            "paciente",
        ).filter(
            eliminado_en__isnull=True,
            paciente__eliminado_en__isnull=True,
        )

        paciente_id = self.request.query_params.get("paciente")
        if paciente_id:
            queryset = queryset.filter(paciente_id=paciente_id)

        return queryset.order_by("-fecha_inicio")

class TipoArchivoDocumentoViewSet(SoftDeleteModelViewSet):
    serializer_class = TipoArchivoDocumentoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TipoArchivoDocumento.objects.filter(
            eliminado_en__isnull=True,
            activo=True,
        ).order_by("nombre")
        
class ArchivoDocumentoViewSet(SoftDeleteModelViewSet):
    serializer_class = ArchivoDocumentoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ArchivoDocumento.objects.select_related(
            "paciente",
        ).filter(
            eliminado_en__isnull=True,
            paciente__eliminado_en__isnull=True,
        )

        paciente_id = self.request.query_params.get("paciente")
        if paciente_id:
            queryset = queryset.filter(paciente_id=paciente_id)

        return queryset.order_by("-fecha")


class AlertaClinicaViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        hoy = timezone.now().date()
        limite = hoy + timedelta(days=30)

        vacunas_vencidas = Vacuna.objects.select_related(
            "paciente",
        ).filter(
            eliminado_en__isnull=True,
            paciente__eliminado_en__isnull=True,
            proxima_dosis__isnull=False,
            proxima_dosis__lt=hoy,
        ).order_by("proxima_dosis")

        vacunas_proximas = Vacuna.objects.select_related(
            "paciente",
        ).filter(
            eliminado_en__isnull=True,
            paciente__eliminado_en__isnull=True,
            proxima_dosis__isnull=False,
            proxima_dosis__gte=hoy,
            proxima_dosis__lte=limite,
        ).order_by("proxima_dosis")

        tratamientos_activos = Tratamiento.objects.select_related(
            "paciente",
        ).filter(
            eliminado_en__isnull=True,
            paciente__eliminado_en__isnull=True,
            fecha_inicio__lte=hoy,
        ).filter(
            models.Q(fecha_fin__isnull=True) | models.Q(fecha_fin__gte=hoy)
        ).order_by("fecha_fin", "-fecha_inicio")

        return Response({
            "fecha_revision": hoy,
            "limite_revision": limite,
            "resumen": {
                "vacunas_vencidas": vacunas_vencidas.count(),
                "vacunas_proximas": vacunas_proximas.count(),
                "tratamientos_activos": tratamientos_activos.count(),
            },
            "vacunas_vencidas": VacunaSerializer(vacunas_vencidas, many=True).data,
            "vacunas_proximas": VacunaSerializer(vacunas_proximas, many=True).data,
            "tratamientos_activos": TratamientoSerializer(tratamientos_activos, many=True).data,
        })