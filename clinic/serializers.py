"""
Serializers de la API de Veterinaria Scarlet.

Responsabilidades:
  - Convertir modelos a/desde JSON
  - Validar datos de entrada (campo a campo y validaciones cruzadas)
  - Exponer solo los campos necesarios al cliente

Los campos de auditoría (eliminado_en) nunca se exponen al cliente.
"""

from datetime import date
import re

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email

from rest_framework import serializers

from .models import (
    ArchivoDocumento,
    Cita,
    Clinica,
    Especie,
    FichaClinica,
    Paciente,
    PerfilUsuario,
    SexoPaciente,
    TipoArchivoDocumento,
    Tratamiento,
    Tutor,
    Vacuna,
)

# Campos de auditoría que nunca se exponen al cliente
AUDIT_FIELDS = ("eliminado_en",)

# Campos de solo lectura comunes a todos los modelos
BASE_READ_ONLY = ("id", "creado_en", "actualizado_en")

# Campo tenant — siempre read-only; se asigna en perform_create del mixin
TENANT_READ_ONLY = ("clinica",)


# ─── Clinica ──────────────────────────────────────────────────────────────────

class ClinicaSerializer(serializers.ModelSerializer):
    """Serializer mínimo para exponer datos de la clínica (p.ej. en /me/)."""

    class Meta:
        model = Clinica
        fields = ("id", "nombre", "email_admin")
        read_only_fields = ("id", "nombre", "email_admin")


class ClinicaEditSerializer(serializers.ModelSerializer):
    """Serializer para editar los datos de la clínica (solo admins)."""

    class Meta:
        model = Clinica
        fields = ("id", "nombre", "email_admin", "creado_en")
        read_only_fields = ("id", "creado_en")

    def validate_nombre(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("El nombre de la clínica no puede estar vacío.")
        if len(value) > 150:
            raise serializers.ValidationError("El nombre no puede superar los 150 caracteres.")
        return value

    def validate_email_admin(self, value):
        value = value.strip().lower()
        if not value:
            raise serializers.ValidationError("El email no puede estar vacío.")
        # Validar formato antes de verificar unicidad
        try:
            validate_email(value)
        except DjangoValidationError:
            raise serializers.ValidationError("El correo electrónico no tiene un formato válido.")
        # Verificar unicidad excluyendo la instancia actual
        qs = Clinica.objects.filter(email_admin__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Este email ya está en uso por otra clínica.")
        return value


# ─── Catálogos ────────────────────────────────────────────────────────────────

class _SoftDeleteNombreValidatorMixin:
    """
    Mixin para serializers de catálogos con unique_together (nombre, clinica).

    Detecta conflictos con registros soft-deleted y devuelve un mensaje
    descriptivo en lugar de un IntegrityError crudo.

    Subclases deben definir `_modelo`, `_nombre_entidad` y `_articulo`.
    """
    _modelo = None          # Clase del modelo (ej. Especie)
    _nombre_entidad = ""    # Nombre legible para el mensaje de error (ej. "especie")
    _articulo = "un"        # Artículo gramatical: "un" o "una"

    def validate_nombre(self, value):
        value = value.strip()
        if self.instance:
            clinica = self.instance.clinica
        else:
            request = self.context.get("request")
            if request is None:
                return value  # Sin contexto de request (tests unitarios), omitir validación
            try:
                clinica = request.user.perfil.clinica
            except (AttributeError, PerfilUsuario.DoesNotExist):
                return value
        qs = self._modelo.all_objects.filter(nombre__iexact=value, clinica=clinica)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        conflicto = qs.first()
        if conflicto is None:
            return value
        if conflicto.eliminado_en is not None:
            raise serializers.ValidationError(
                f"Ya existe {self._articulo} {self._nombre_entidad} llamado"
                f"{'a' if self._articulo == 'una' else ''} '{value}' que fue eliminado"
                f"{'a' if self._articulo == 'una' else ''}. "
                "Contacta al administrador para restaurarlo."
            )
        raise serializers.ValidationError(
            f"Ya existe {self._articulo} {self._nombre_entidad} con ese nombre."
        )


class EspecieSerializer(_SoftDeleteNombreValidatorMixin, serializers.ModelSerializer):
    _modelo = Especie
    _nombre_entidad = "especie"
    _articulo = "una"

    class Meta:
        model = Especie
        exclude = AUDIT_FIELDS
        read_only_fields = (*BASE_READ_ONLY, *TENANT_READ_ONLY)


class SexoPacienteSerializer(_SoftDeleteNombreValidatorMixin, serializers.ModelSerializer):
    _modelo = SexoPaciente
    _nombre_entidad = "sexo"
    _articulo = "un"

    class Meta:
        model = SexoPaciente
        exclude = AUDIT_FIELDS
        read_only_fields = (*BASE_READ_ONLY, *TENANT_READ_ONLY)


class TipoArchivoDocumentoSerializer(_SoftDeleteNombreValidatorMixin, serializers.ModelSerializer):
    _modelo = TipoArchivoDocumento
    _nombre_entidad = "tipo de archivo"
    _articulo = "un"

    class Meta:
        model = TipoArchivoDocumento
        exclude = AUDIT_FIELDS
        read_only_fields = (*BASE_READ_ONLY, *TENANT_READ_ONLY)


# ─── Entidades principales ────────────────────────────────────────────────────

class TutorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tutor
        exclude = AUDIT_FIELDS
        read_only_fields = (*BASE_READ_ONLY, *TENANT_READ_ONLY)

    def validate_rut(self, value):
        """Valida formato y dígito verificador del RUT chileno: 12345678-9 o 1234567-K."""
        if value is None or value == "":
            return value
        value = value.strip().upper()
        if not re.match(r"^\d{1,8}-[\dK]$", value):
            raise serializers.ValidationError(
                "Formato de RUT inválido. Use el formato 12345678-9."
            )
        # Validar dígito verificador con módulo 11
        cuerpo, dv_ingresado = value.split("-")
        suma = 0
        multiplicador = 2
        for digito in reversed(cuerpo):
            suma += int(digito) * multiplicador
            multiplicador = multiplicador + 1 if multiplicador < 7 else 2
        resto = suma % 11
        dv_calculado = "K" if resto == 1 else ("0" if resto == 0 else str(11 - resto))
        if dv_ingresado != dv_calculado:
            raise serializers.ValidationError(
                f"RUT inválido: el dígito verificador no corresponde."
            )
        return value


class PacienteSerializer(serializers.ModelSerializer):
    # Campos de solo lectura derivados de relaciones
    tutor_nombre = serializers.CharField(source="tutor.nombre", read_only=True)
    especie_nombre = serializers.CharField(source="especie.nombre", read_only=True)
    sexo_nombre = serializers.CharField(source="sexo.nombre", read_only=True)

    class Meta:
        model = Paciente
        exclude = AUDIT_FIELDS
        read_only_fields = (*BASE_READ_ONLY, *TENANT_READ_ONLY, "tutor_nombre", "especie_nombre", "sexo_nombre")

    def validate_fecha_nacimiento(self, value):
        """La fecha de nacimiento no puede ser futura."""
        if value is None:
            return value
        if value > date.today():
            raise serializers.ValidationError(
                "La fecha de nacimiento no puede ser una fecha futura."
            )
        return value


class FichaClinicaSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)

    class Meta:
        model = FichaClinica
        exclude = AUDIT_FIELDS
        read_only_fields = (*BASE_READ_ONLY, *TENANT_READ_ONLY, "paciente_nombre")
        # NOTA: El campo `fecha` es un DateTimeField con USE_TZ=True, por lo que se
        # serializa en UTC (ISO 8601 con 'Z'). El frontend debe convertirlo a la zona
        # horaria local del usuario para mostrarlo correctamente.

    def validate_peso_kg(self, value):
        # Los validators del modelo (MinValueValidator/MaxValueValidator) ya validan
        # los rangos, pero DRF solo los llama en full_clean(). Estos métodos dan
        # mensajes de error más descriptivos en la respuesta de la API.
        if value is not None and value <= 0:
            raise serializers.ValidationError("El peso debe ser mayor a 0.")
        return value

    def validate_temperatura(self, value):
        if value is not None and not (25.0 <= float(value) <= 45.0):
            raise serializers.ValidationError(
                "La temperatura debe estar entre 25.0 °C y 45.0 °C."
            )
        return value

    def validate_frecuencia_cardiaca(self, value):
        if value is not None and not (1 <= value <= 500):
            raise serializers.ValidationError(
                "La frecuencia cardíaca debe estar entre 1 y 500 lpm."
            )
        return value

    def validate_frecuencia_respiratoria(self, value):
        if value is not None and not (1 <= value <= 200):
            raise serializers.ValidationError(
                "La frecuencia respiratoria debe estar entre 1 y 200 rpm."
            )
        return value


class CitaSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)
    tutor_nombre = serializers.CharField(source="tutor.nombre", read_only=True)

    class Meta:
        model = Cita
        exclude = AUDIT_FIELDS
        read_only_fields = (*BASE_READ_ONLY, *TENANT_READ_ONLY, "paciente_nombre", "tutor_nombre")
        # DRF valida los choices automáticamente — validate_estado no es necesario


class VacunaSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)

    class Meta:
        model = Vacuna
        exclude = AUDIT_FIELDS
        read_only_fields = (*BASE_READ_ONLY, *TENANT_READ_ONLY, "paciente_nombre")

    def validate(self, attrs):
        """proxima_dosis debe ser posterior a fecha_aplicacion."""
        fecha_aplicacion = attrs.get("fecha_aplicacion")
        proxima_dosis = attrs.get("proxima_dosis")

        if fecha_aplicacion and proxima_dosis:
            if proxima_dosis <= fecha_aplicacion:
                raise serializers.ValidationError(
                    {"proxima_dosis": "La próxima dosis debe ser posterior a la fecha de aplicación."}
                )
        return attrs


class TratamientoSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)

    class Meta:
        model = Tratamiento
        exclude = AUDIT_FIELDS
        read_only_fields = (*BASE_READ_ONLY, *TENANT_READ_ONLY, "paciente_nombre")

    def validate(self, attrs):
        """fecha_fin debe ser igual o posterior a fecha_inicio."""
        fecha_inicio = attrs.get("fecha_inicio")
        fecha_fin = attrs.get("fecha_fin")

        if fecha_inicio and fecha_fin:
            if fecha_fin < fecha_inicio:
                raise serializers.ValidationError(
                    {"fecha_fin": "La fecha de fin debe ser igual o posterior a la fecha de inicio."}
                )
        return attrs


class ArchivoDocumentoSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)
    tipo_nombre = serializers.CharField(source="tipo.nombre", read_only=True)

    class Meta:
        model = ArchivoDocumento
        exclude = AUDIT_FIELDS
        read_only_fields = (*BASE_READ_ONLY, *TENANT_READ_ONLY, "paciente_nombre", "tipo_nombre")

    def validate_archivo_url(self, value):
        """La URL del archivo debe ser HTTPS en producción."""
        if value and not value.startswith(("https://", "http://")):
            raise serializers.ValidationError(
                "La URL del archivo debe comenzar con http:// o https://."
            )
        return value


# ─── Serializer de detalle de ficha ──────────────────────────────────────────

class FichaClinicaDetalleSerializer(serializers.ModelSerializer):
    """
    Serializer completo para GET /fichas/{id}/.

    Incluye el paciente anidado (con tutor_nombre, especie_nombre, etc. ya dentro)
    y sus vacunas, tratamientos, archivos e historial de fichas.
    El ViewSet hace prefetch_related de estas relaciones para que los métodos
    get_* operen sobre la caché en memoria sin queries adicionales.
    """

    paciente = PacienteSerializer(read_only=True)
    fecha_nacimiento = serializers.DateField(source="paciente.fecha_nacimiento", read_only=True)

    # Campos aplanados del paciente para acceso directo desde el frontend
    paciente_nombre = serializers.CharField(source="paciente.nombre", read_only=True)
    tutor_nombre = serializers.CharField(source="paciente.tutor.nombre", read_only=True)
    especie_nombre = serializers.CharField(source="paciente.especie.nombre", read_only=True)
    sexo_nombre = serializers.CharField(source="paciente.sexo.nombre", read_only=True)

    vacunas = serializers.SerializerMethodField()
    tratamientos = serializers.SerializerMethodField()
    archivos = serializers.SerializerMethodField()
    historial_fichas = serializers.SerializerMethodField()

    class Meta:
        model = FichaClinica
        exclude = AUDIT_FIELDS
        read_only_fields = (
            *BASE_READ_ONLY,
            *TENANT_READ_ONLY,
            "paciente_nombre", "tutor_nombre", "especie_nombre", "sexo_nombre",
            "vacunas", "tratamientos", "archivos", "historial_fichas",
        )

    # Los métodos filtran sobre el prefetch_related del ViewSet (sin queries extra).

    def get_vacunas(self, obj):
        # El Prefetch en FichaClinicaViewSet ya filtra eliminado_en__isnull=True.
        # El modelo Vacuna tiene Meta.ordering = ["-fecha_aplicacion"], así que
        # el queryset ya viene ordenado correctamente desde la DB.
        return VacunaSerializer(obj.paciente.vacunas.all(), many=True, context=self.context).data

    def get_tratamientos(self, obj):
        return TratamientoSerializer(obj.paciente.tratamientos.all(), many=True, context=self.context).data

    def get_archivos(self, obj):
        return ArchivoDocumentoSerializer(obj.paciente.archivos.all(), many=True, context=self.context).data

    def get_historial_fichas(self, obj):
        # Excluir la ficha actual del historial
        qs = [f for f in obj.paciente.fichas.all() if f.id != obj.id]
        return FichaClinicaSerializer(qs, many=True, context=self.context).data
