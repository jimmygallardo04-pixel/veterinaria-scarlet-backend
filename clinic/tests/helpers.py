"""
Funciones helper para crear fixtures de test reutilizables.

Todas las funciones usan get_or_create o create directamente según
si el dato debe ser único (catálogos) o puede repetirse (entidades).
"""

from django.contrib.auth.models import User
from django.utils import timezone

from clinic.models import (
    Cita,
    Clinica,
    Especie,
    FichaClinica,
    Paciente,
    SexoPaciente,
    Tratamiento,
    Tutor,
    Vacuna,
)


def make_clinica(nombre: str = "Clínica Test") -> Clinica:
    """Crea o recupera una clínica de prueba."""
    clinica, _ = Clinica.objects.get_or_create(
        email_admin=f"test_{nombre.lower().replace(' ', '_')}@test.cl",
        defaults={"nombre": nombre, "activo": True},
    )
    return clinica


def make_user(username: str = "testuser", password: str = "testpass123", clinica=None) -> User:
    from clinic.models import PerfilUsuario
    user, created = User.objects.get_or_create(username=username)
    user.set_password(password)
    user.save()
    if clinica is not None:
        PerfilUsuario.objects.get_or_create(
            user=user,
            defaults={"clinica": clinica, "rol": PerfilUsuario.Rol.ADMIN},
        )
    return user


def make_especie(nombre: str = "Perro", clinica: Clinica | None = None) -> Especie:
    if clinica is None:
        clinica = make_clinica()
    especie, _ = Especie.objects.get_or_create(nombre=nombre, clinica=clinica)
    return especie


def make_sexo(nombre: str = "Macho", clinica: Clinica | None = None) -> SexoPaciente:
    if clinica is None:
        clinica = make_clinica()
    sexo, _ = SexoPaciente.objects.get_or_create(nombre=nombre, clinica=clinica)
    return sexo


def make_tutor(
    nombre: str = "Tutor Test",
    telefono: str = "123456789",
    clinica: Clinica | None = None,
) -> Tutor:
    if clinica is None:
        clinica = make_clinica()
    return Tutor.objects.create(nombre=nombre, telefono=telefono, clinica=clinica)


def make_paciente(
    tutor: Tutor,
    nombre: str = "Paciente Test",
    clinica: Clinica | None = None,
) -> Paciente:
    if clinica is None:
        clinica = tutor.clinica
    return Paciente.objects.create(
        tutor=tutor,
        nombre=nombre,
        especie=make_especie(clinica=clinica),
        sexo=make_sexo(clinica=clinica),
        clinica=clinica,
    )


def make_cita(
    paciente: Paciente,
    tutor: Tutor,
    motivo: str = "Consulta general",
    estado: str = "pendiente",
    clinica: Clinica | None = None,
) -> Cita:
    if clinica is None:
        clinica = paciente.clinica
    return Cita.objects.create(
        paciente=paciente,
        tutor=tutor,
        fecha_hora=timezone.now(),
        motivo=motivo,
        estado=estado,
        clinica=clinica,
    )


def make_vacuna(
    paciente: Paciente,
    dias_hasta_proxima: int = 30,
    clinica: Clinica | None = None,
) -> Vacuna:
    from datetime import date, timedelta
    if clinica is None:
        clinica = paciente.clinica
    hoy = date.today()
    return Vacuna.objects.create(
        paciente=paciente,
        nombre_vacuna="Rabia",
        fecha_aplicacion=hoy - timedelta(days=1),
        proxima_dosis=hoy + timedelta(days=dias_hasta_proxima),
        clinica=clinica,
    )


def make_tratamiento(
    paciente: Paciente,
    dias_inicio: int = -1,
    dias_fin: int = 10,
    clinica: Clinica | None = None,
) -> Tratamiento:
    from datetime import date, timedelta
    if clinica is None:
        clinica = paciente.clinica
    hoy = date.today()
    return Tratamiento.objects.create(
        paciente=paciente,
        medicamento="Amoxicilina",
        dosis="250mg",
        frecuencia="Cada 8 horas",
        fecha_inicio=hoy + timedelta(days=dias_inicio),
        fecha_fin=hoy + timedelta(days=dias_fin),
        clinica=clinica,
    )
