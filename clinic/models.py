from datetime import date
from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    eliminado_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        self.eliminado_en = timezone.now()
        self.save(update_fields=["eliminado_en", "actualizado_en"])


class Tutor(BaseModel):
    nombre = models.CharField(max_length=150)
    rut = models.CharField(max_length=20, blank=True, null=True)
    telefono = models.CharField(max_length=30)
    email = models.EmailField(blank=True, null=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.nombre

class Especie(BaseModel):
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre


class SexoPaciente(BaseModel):
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class Paciente(BaseModel):
    tutor = models.ForeignKey(Tutor, on_delete=models.CASCADE, related_name="pacientes")
    nombre = models.CharField(max_length=100)
    especie = models.ForeignKey(Especie, on_delete=models.CASCADE, related_name="pacientes")
    raza = models.CharField(max_length=100, blank=True, null=True)
    sexo = models.ForeignKey(SexoPaciente, on_delete=models.CASCADE, related_name="pacientes")
    fecha_nacimiento = models.DateField(blank=True, null=True)
    color = models.CharField(max_length=100, blank=True, null=True)
    esterilizado = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True, null=True)

    @property
    def edad(self):
        if not self.fecha_nacimiento:
            return None

        hoy = date.today()
        return (
            hoy.year
            - self.fecha_nacimiento.year
            - ((hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))
        )

    def __str__(self):
        return f"{self.nombre} - {self.tutor.nombre}"


class FichaClinica(BaseModel):
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="fichas")

    fecha = models.DateTimeField(default=timezone.now)
    motivo_consulta = models.TextField()
    anamnesis = models.TextField(blank=True, null=True)

    peso_kg = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    temperatura = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    frecuencia_cardiaca = models.PositiveIntegerField(blank=True, null=True)
    frecuencia_respiratoria = models.PositiveIntegerField(blank=True, null=True)

    diagnostico = models.TextField(blank=True, null=True)
    tratamiento = models.TextField(blank=True, null=True)
    indicaciones = models.TextField(blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Ficha {self.paciente.nombre} - {self.fecha.date()}"


class Cita(BaseModel):
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("completada", "Completada"),
        ("cancelada", "Cancelada"),
    ]

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="citas")
    tutor = models.ForeignKey(Tutor, on_delete=models.CASCADE, related_name="citas")

    fecha_hora = models.DateTimeField()
    motivo = models.CharField(max_length=255)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Cita {self.paciente.nombre} - {self.fecha_hora}"


class Vacuna(BaseModel):
    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.CASCADE,
        related_name="vacunas"
    )

    nombre_vacuna = models.CharField(max_length=150)
    fecha_aplicacion = models.DateField()
    proxima_dosis = models.DateField(blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.nombre_vacuna} - {self.paciente.nombre}"


class Tratamiento(BaseModel):
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="tratamientos")

    medicamento = models.CharField(max_length=150)
    dosis = models.CharField(max_length=100)
    frecuencia = models.CharField(max_length=100)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(blank=True, null=True)
    indicaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.medicamento} - {self.paciente.nombre}"


class TipoArchivoDocumento(BaseModel):
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre


class ArchivoDocumento(BaseModel):
    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.CASCADE,
        related_name="archivos"
    )

    tipo = models.ForeignKey(
        TipoArchivoDocumento,
        on_delete=models.PROTECT,
        related_name="archivos"
    )

    archivo_url = models.URLField()
    storage_path = models.CharField(max_length=500, blank=True, null=True)

    fecha = models.DateField(default=timezone.now)
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.tipo.nombre} - {self.paciente.nombre}"
