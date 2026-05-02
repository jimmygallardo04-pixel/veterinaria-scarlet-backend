from rest_framework import serializers

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
    TipoArchivoDocumento,
)


class TutorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tutor
        fields = "__all__"


class EspecieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Especie
        fields = "__all__"


class SexoPacienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = SexoPaciente
        fields = "__all__"


class PacienteSerializer(serializers.ModelSerializer):
    tutor_nombre = serializers.CharField(source="tutor.nombre", read_only=True)
    especie_nombre = serializers.CharField(source="especie.nombre", read_only=True)
    sexo_nombre = serializers.CharField(source="sexo.nombre", read_only=True)
    edad = serializers.ReadOnlyField()

    class Meta:
        model = Paciente
        fields = "__all__"


class FichaClinicaSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)

    class Meta:
        model = FichaClinica
        fields = "__all__"


class CitaSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)
    tutor_nombre = serializers.CharField(source="tutor.nombre", read_only=True)

    class Meta:
        model = Cita
        fields = "__all__"


class VacunaSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)

    class Meta:
        model = Vacuna
        fields = "__all__"


class TratamientoSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)

    class Meta:
        model = Tratamiento
        fields = "__all__"

class TipoArchivoDocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoArchivoDocumento
        fields = "__all__"

class ArchivoDocumentoSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)
    tipo_nombre = serializers.CharField(source="tipo.nombre", read_only=True)

    class Meta:
        model = ArchivoDocumento
        fields = "__all__"


class FichaClinicaDetalleSerializer(serializers.ModelSerializer):
    paciente = PacienteSerializer(read_only=True)

    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)
    tutor_nombre = serializers.CharField(source="paciente.tutor.nombre", read_only=True)
    especie_nombre = serializers.CharField(source="paciente.especie.nombre", read_only=True)
    sexo_nombre = serializers.CharField(source="paciente.sexo.nombre", read_only=True)
    edad = serializers.ReadOnlyField(source="paciente.edad")

    vacunas = serializers.SerializerMethodField()
    tratamientos = serializers.SerializerMethodField()
    archivos = serializers.SerializerMethodField()
    historial_fichas = serializers.SerializerMethodField()

    class Meta:
        model = FichaClinica
        fields = "__all__"

    def get_vacunas(self, obj):
        vacunas = obj.paciente.vacunas.filter(
            eliminado_en__isnull=True
        ).order_by("-fecha_aplicacion")

        return VacunaSerializer(vacunas, many=True).data

    def get_tratamientos(self, obj):
        tratamientos = obj.paciente.tratamientos.filter(
            eliminado_en__isnull=True
        ).order_by("-fecha_inicio")

        return TratamientoSerializer(tratamientos, many=True).data

    def get_archivos(self, obj):
        archivos = obj.paciente.archivos.filter(
            eliminado_en__isnull=True
        ).order_by("-fecha")

        return ArchivoDocumentoSerializer(archivos, many=True).data

    def get_historial_fichas(self, obj):
        fichas = obj.paciente.fichas.filter(
            eliminado_en__isnull=True
        ).exclude(
            id=obj.id
        ).order_by("-fecha")

        return FichaClinicaSerializer(fichas, many=True).data