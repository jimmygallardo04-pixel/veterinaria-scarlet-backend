import logging
import uuid
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .managers import ActiveManager, AllObjectsManager

logger = logging.getLogger(__name__)

# ─── Multi-tenancy ────────────────────────────────────────────────────────────

class Clinica(models.Model):
    uuid        = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nombre      = models.CharField(max_length=150)
    email_admin = models.EmailField(unique=True)
    creado_en   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class PerfilUsuario(models.Model):
    class Rol(models.TextChoices):
        ADMIN       = "admin",       "Administrador"
        VETERINARIO = "veterinario", "Veterinario"

    user    = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil",
    )
    clinica = models.ForeignKey(
        Clinica,
        on_delete=models.CASCADE,
        related_name="perfiles",
    )
    rol     = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.VETERINARIO,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user"], name="unique_perfil_por_usuario")
        ]

    def __str__(self) -> str:
        return f"{self.user.email} — {self.clinica.nombre} ({self.rol})"


# ─── Base ─────────────────────────────────────────────────────────────────────

class BaseModel(models.Model):
    """
    Modelo base con timestamps y soporte de soft-delete.

    Todos los modelos del dominio heredan de esta clase.
    - `objects`     → solo registros activos (sin soft-delete)
    - `all_objects` → todos los registros, incluyendo eliminados
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    eliminado_en = models.DateTimeField(blank=True, null=True)

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        """Marca el registro como eliminado sin borrarlo de la base de datos."""
        self.eliminado_en = timezone.now()
        self.save(update_fields=["eliminado_en", "actualizado_en"])

    def is_active(self) -> bool:
        """Devuelve True si el registro no ha sido eliminado."""
        return self.eliminado_en is None

    def regenerate_uuid(self, reason: str = "security") -> None:
        """
        Regenera el UUID del recurso. Solo para emergencias (exposición, breach).

        Args:
            reason: Razón de la regeneración ("exposure", "security_breach", "ownership_change", etc.)

        Warning:
            Cambiar el UUID rompe referencias existentes. Solo usar en emergencias.
        """
        if self.uuid is None:
            raise ValueError("No existe UUID para regenerar")

        from django.contrib.auth.models import User
        from django.utils import timezone

        old_uuid = self.uuid
        self.uuid = uuid.uuid4()

        # Registrar cambio en historial (si el modelo lo soporta)
        if hasattr(self, 'uuid_anterior'):
            self.uuid_anterior = old_uuid

        self.save(update_fields=['uuid'] + (['uuid_anterior'] if hasattr(self, 'uuid_anterior') else []))

        logger.warning(
            f"UUID regenerated for {self.__class__.__name__} (id={self.pk}): "
            f"{old_uuid} → {self.uuid} (reason: {reason})"
        )


# ─── Catálogos ────────────────────────────────────────────────────────────────

class Especie(BaseModel):
    """
    Catálogo de especies animales.

    El estado activo/inactivo se gestiona exclusivamente mediante soft-delete
    (campo `eliminado_en` heredado de BaseModel). Un registro con
    `eliminado_en` no nulo está "eliminado" y el ActiveManager lo excluye
    automáticamente de todos los querysets.

    Nota sobre unicidad y soft-delete: `unique_together` aplica a todos los
    registros incluyendo los soft-deleted. Si se elimina "Perro" y se intenta
    crear de nuevo, el serializer detecta el conflicto y devuelve un error
    descriptivo en lugar de un IntegrityError crudo.
    """
    clinica = models.ForeignKey(
        "Clinica", on_delete=models.CASCADE, db_index=True
    )
    nombre = models.CharField(max_length=100, db_index=True)

    class Meta:
        ordering = ["nombre"]
        unique_together = [("nombre", "clinica")]

    def __str__(self) -> str:
        return self.nombre


class SexoPaciente(BaseModel):
    """
    Catálogo de sexos de paciente.

    Estado activo/inactivo gestionado por soft-delete (ver BaseModel).
    """
    clinica = models.ForeignKey(
        "Clinica", on_delete=models.CASCADE, db_index=True
    )
    nombre = models.CharField(max_length=100, db_index=True)

    class Meta:
        ordering = ["nombre"]
        unique_together = [("nombre", "clinica")]

    def __str__(self) -> str:
        return self.nombre


class TipoArchivoDocumento(BaseModel):
    """
    Catálogo de tipos de archivo/documento clínico.

    Estado activo/inactivo gestionado por soft-delete (ver BaseModel).
    """
    clinica = models.ForeignKey(
        "Clinica", on_delete=models.CASCADE, db_index=True
    )
    nombre = models.CharField(max_length=100, db_index=True)

    class Meta:
        ordering = ["nombre"]
        unique_together = [("nombre", "clinica")]

    def __str__(self) -> str:
        return self.nombre


# ─── Entidades principales ────────────────────────────────────────────────────

class Tutor(BaseModel):
    clinica = models.ForeignKey(
        "Clinica", on_delete=models.CASCADE, db_index=True
    )
    nombre = models.CharField(max_length=150, db_index=True)
    rut = models.CharField(max_length=20, blank=True, null=True)
    telefono = models.CharField(max_length=30)
    email = models.EmailField(blank=True, null=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    activo = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Paciente(BaseModel):
    clinica = models.ForeignKey(
        "Clinica", on_delete=models.CASCADE, db_index=True
    )
    tutor = models.ForeignKey(Tutor, on_delete=models.CASCADE, related_name="pacientes")
    nombre = models.CharField(max_length=100, db_index=True)
    especie = models.ForeignKey(Especie, on_delete=models.CASCADE, related_name="pacientes")
    raza = models.CharField(max_length=100, blank=True, null=True)
    sexo = models.ForeignKey(SexoPaciente, on_delete=models.CASCADE, related_name="pacientes")
    fecha_nacimiento = models.DateField(blank=True, null=True)
    color = models.CharField(max_length=100, blank=True, null=True)
    esterilizado = models.BooleanField(default=False)
    chip = models.CharField(max_length=25, blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]

    @property
    def edad(self) -> int | None:
        """Edad en años completos, o None si no tiene fecha de nacimiento."""
        if not self.fecha_nacimiento:
            return None
        hoy = date.today()
        return (
            hoy.year
            - self.fecha_nacimiento.year
            - ((hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))
        )

    def __str__(self) -> str:
        return f"{self.nombre} - {self.tutor.nombre}"


class FichaClinica(BaseModel):
    clinica = models.ForeignKey(
        "Clinica", on_delete=models.CASCADE, db_index=True
    )
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="fichas")

    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    motivo_consulta = models.TextField()
    anamnesis = models.TextField(blank=True, null=True)

    # Signos vitales con rangos clínicamente razonables.
    # Los límites usan Decimal para que DRF no emita warnings al serializar.
    peso_kg = models.DecimalField(
        max_digits=6, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("999.99"))],
        help_text="Peso en kg (0.01 – 999.99)",
    )
    temperatura = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("25.0")), MaxValueValidator(Decimal("45.0"))],
        help_text="Temperatura corporal en °C (25.0 – 45.0)",
    )
    frecuencia_cardiaca = models.PositiveIntegerField(
        blank=True, null=True,
        validators=[MinValueValidator(1), MaxValueValidator(500)],
        help_text="Frecuencia cardíaca en lpm (1 – 500)",
    )
    frecuencia_respiratoria = models.PositiveIntegerField(
        blank=True, null=True,
        validators=[MinValueValidator(1), MaxValueValidator(200)],
        help_text="Frecuencia respiratoria en rpm (1 – 200)",
    )

    diagnostico = models.TextField(blank=True, null=True)
    # tratamiento e indicaciones son campos de texto libre para notas rápidas
    # en la ficha. El modelo Tratamiento (con medicamento, dosis, frecuencia)
    # es la fuente de verdad para tratamientos estructurados y seguimiento.
    tratamiento = models.TextField(blank=True, null=True)
    indicaciones = models.TextField(blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self) -> str:
        return f"Ficha {self.paciente.nombre} - {self.fecha.date()}"


class Cita(BaseModel):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        COMPLETADA = "completada", "Completada"
        CANCELADA = "cancelada", "Cancelada"

    clinica = models.ForeignKey(
        "Clinica", on_delete=models.CASCADE, db_index=True
    )
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="citas")
    # tutor se almacena directamente para preservar el registro histórico:
    # si el tutor de un paciente cambia, la cita mantiene el tutor original.
    tutor = models.ForeignKey(Tutor, on_delete=models.CASCADE, related_name="citas")

    fecha_hora = models.DateTimeField(db_index=True)
    motivo = models.CharField(max_length=255)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
        db_index=True,
    )
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-fecha_hora"]

    def __str__(self) -> str:
        return f"Cita {self.paciente.nombre} - {self.fecha_hora}"


class Vacuna(BaseModel):
    clinica = models.ForeignKey(
        "Clinica", on_delete=models.CASCADE, db_index=True
    )
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="vacunas")

    nombre_vacuna = models.CharField(max_length=150)
    fecha_aplicacion = models.DateField(db_index=True)
    proxima_dosis = models.DateField(blank=True, null=True, db_index=True)
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-fecha_aplicacion"]

    def clean(self) -> None:
        """proxima_dosis debe ser posterior a fecha_aplicacion."""
        if self.proxima_dosis and self.fecha_aplicacion:
            if self.proxima_dosis <= self.fecha_aplicacion:
                raise ValidationError(
                    {"proxima_dosis": "La próxima dosis debe ser posterior a la fecha de aplicación."}
                )

    def __str__(self) -> str:
        return f"{self.nombre_vacuna} - {self.paciente.nombre}"


class Tratamiento(BaseModel):
    clinica = models.ForeignKey(
        "Clinica", on_delete=models.CASCADE, db_index=True
    )
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="tratamientos")
    ficha_clinica = models.ForeignKey(
        FichaClinica,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name="tratamientos_asociados",
        help_text="Ficha clínica desde la cual se originó este tratamiento (opcional)"
    )

    medicamento = models.CharField(max_length=150)
    dosis = models.CharField(max_length=100)
    frecuencia = models.CharField(max_length=100)
    fecha_inicio = models.DateField(db_index=True)
    fecha_fin = models.DateField(blank=True, null=True)
    indicaciones = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-fecha_inicio"]

    def clean(self) -> None:
        """fecha_fin debe ser igual o posterior a fecha_inicio."""
        if self.fecha_fin and self.fecha_inicio:
            if self.fecha_fin < self.fecha_inicio:
                raise ValidationError(
                    {"fecha_fin": "La fecha de fin debe ser igual o posterior a la fecha de inicio."}
                )

        # Validar que la ficha pertenece al mismo paciente
        if self.ficha_clinica and self.ficha_clinica.paciente_id != self.paciente_id:
            raise ValidationError(
                {"ficha_clinica": "La ficha clínica debe pertenecer al mismo paciente."}
            )

    def __str__(self) -> str:
        return f"{self.medicamento} - {self.paciente.nombre}"


class ArchivoDocumento(BaseModel):
    clinica = models.ForeignKey(
        "Clinica", on_delete=models.CASCADE, db_index=True
    )
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="archivos")
    tipo = models.ForeignKey(TipoArchivoDocumento, on_delete=models.PROTECT, related_name="archivos")

    archivo_url = models.URLField()
    storage_path = models.CharField(max_length=500, blank=True, null=True)

    # date.today() usa la fecha local del servidor (America/Santiago con USE_TZ=True).
    # timezone.now() devolvería la fecha UTC, que puede diferir de la local en la noche.
    fecha = models.DateField(default=date.today, db_index=True)
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self) -> str:
        return f"{self.tipo.nombre} - {self.paciente.nombre}"


# ─── Verificación de email ────────────────────────────────────────────────────

class CodigoVerificacion(models.Model):
    """
    Código OTP de 6 dígitos para verificar el email antes del registro.

    - Se genera uno nuevo por cada solicitud (invalida los anteriores).
    - Expira a los 15 minutos.
    - Se marca como usado al validarse correctamente.
    - Tras OTP_MAX_INTENTOS intentos fallidos el código queda bloqueado.
    """

    email = models.EmailField(db_index=True)
    codigo = models.CharField(max_length=6)
    creado_en = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField()
    usado = models.BooleanField(default=False)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["email", "usado"], name="idx_codigo_email_usado"),
            models.Index(fields=["email", "creado_en"], name="idx_codigo_email_creado"),
            models.Index(fields=["expira_en"], name="idx_codigo_expira_en"),
            # Cubre la query de email_esta_verificado: filter(email, usado=True, creado_en__gte)
            models.Index(fields=["email", "usado", "creado_en"], name="idx_codigo_verificado"),
        ]

    def __str__(self) -> str:
        return f"Código para {self.email} ({'usado' if self.usado else 'pendiente'})"

    def is_valid(self) -> bool:
        """Devuelve True si el código no ha expirado y no está bloqueado por intentos.

        Nota: el estado `usado` se controla externamente filtrando `usado=False`
        en la query, por lo que no es necesario verificarlo aquí.
        """
        max_intentos = getattr(settings, "OTP_MAX_INTENTOS", 3)
        return (
            self.intentos_fallidos < max_intentos
            and timezone.now() <= self.expira_en
        )
