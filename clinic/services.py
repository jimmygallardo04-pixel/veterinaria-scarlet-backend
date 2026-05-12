"""
Capa de servicios — lógica de negocio desacoplada de las vistas HTTP.

Las funciones aquí son reutilizables desde vistas, comandos de management,
tareas Celery o tests sin necesidad de simular requests HTTP.

Módulos:
    - Registro de clínica
    - Búsqueda de pacientes
    - Alertas clínicas
"""

import logging
import secrets
import string
from dataclasses import dataclass
from datetime import date, timedelta
from html import escape as html_escape

from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import F, Q, QuerySet
from django.utils import timezone

import resend

from rest_framework_simplejwt.tokens import RefreshToken

from .models import Clinica, CodigoVerificacion, Paciente, PerfilUsuario, Tratamiento, Vacuna

logger = logging.getLogger(__name__)


# ─── Tipos de entrada / salida ────────────────────────────────────────────────

@dataclass
class RegistroClinicaInput:
    nombre_clinica: str
    nombre_admin: str
    email: str
    password: str


@dataclass
class RegistroClinicaResult:
    user: User
    clinica: "Clinica"
    access_token: str
    refresh_token: str


@dataclass
class AlertasClinicaResult:
    fecha_revision: date
    limite_revision: date
    vacunas_vencidas: QuerySet
    vacunas_proximas: QuerySet
    tratamientos_activos: QuerySet


# ─── Errores de dominio ───────────────────────────────────────────────────────

class EmailYaRegistradoError(ValueError):
    """El email ya está asociado a una cuenta existente."""


class EmailFormatoInvalidoError(ValueError):
    """El email no tiene un formato válido."""


class PasswordDemasiadoCortaError(ValueError):
    """La contraseña no cumple el mínimo de longitud."""


class CamposObligatoriosError(ValueError):
    """Uno o más campos obligatorios están vacíos."""


# ─── Servicio de verificación de email ───────────────────────────────────────

class CodigoInvalidoError(ValueError):
    """El código OTP no existe, expiró o ya fue usado."""


class CodigoBloqueadoError(ValueError):
    """El código OTP fue bloqueado por demasiados intentos fallidos."""


def _generar_codigo() -> str:
    """Genera un código numérico de 6 dígitos usando secrets (criptográficamente seguro)."""
    return "".join(secrets.choice(string.digits) for _ in range(6))


def _email_en_uso(email: str, exclude_pk: int | None = None) -> bool:
    """
    Devuelve True si el email ya está registrado como email o username de algún User.
    La comparación es case-insensitive para evitar duplicados por capitalización.

    Args:
        email: El email a verificar.
        exclude_pk: Si se proporciona, excluye ese User del chequeo (útil al editar).
    """
    qs = User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email))
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def solicitar_codigo_verificacion(email: str) -> None:
    """
    Genera un código OTP de 6 dígitos, lo guarda en la DB y lo envía
    al email indicado usando Resend.

    Invalida cualquier código anterior para ese email.
    El código expira en 15 minutos.

    La respuesta es siempre genérica para no revelar si el email existe.

    Raises:
        CamposObligatoriosError: Si el email está vacío o tiene formato inválido.
    """
    if not email:
        raise CamposObligatoriosError("El correo electrónico es obligatorio.")

    # Normalizar a lowercase para consistencia con el registro
    email = email.strip().lower()

    try:
        validate_email(email)
    except DjangoValidationError:
        raise EmailFormatoInvalidoError("El correo electrónico no tiene un formato válido.")

    # Si el email ya tiene cuenta, no enviamos código pero respondemos igual
    # para no revelar qué emails están registrados (evita enumeración).
    if _email_en_uso(email):
        logger.info("Solicitud de código para email ya registrado: %s (ignorada silenciosamente)", email)
        return

    # Invalidar códigos anteriores para este email
    CodigoVerificacion.objects.filter(email=email, usado=False).update(usado=True)

    codigo = _generar_codigo()
    expira_en = timezone.now() + timedelta(minutes=15)

    CodigoVerificacion.objects.create(
        email=email,
        codigo=codigo,
        expira_en=expira_en,
    )

    _enviar_codigo_por_email(email=email, codigo=codigo)
    logger.info("Código de verificación enviado a %s", email)


def _enviar_codigo_por_email(email: str, codigo: str) -> None:
    """
    Envía el código OTP usando la API de Resend.

    Si el envío falla, loguea el error y retorna silenciosamente.
    El código ya fue guardado en la DB — el usuario puede reintentar
    solicitando un nuevo código.
    """
    api_key = django_settings.RESEND_API_KEY
    from_email = django_settings.EMAIL_FROM

    if not api_key:
        logger.warning("RESEND_API_KEY no configurada — código no enviado a %s", email)
        return

    resend.api_key = api_key

    try:
        resend.Emails.send({
            "from": from_email,
            "to": [email],
            "subject": "Tu código de verificación — Veterinaria Scarlet",
            "html": f"""
                <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px">
                  <h2 style="color:#16a34a;margin-bottom:8px">Veterinaria Scarlet</h2>
                  <p style="color:#475569;margin-bottom:24px">
                    Usa el siguiente código para completar tu registro.
                    Expira en <strong>15 minutos</strong>.
                  </p>
                  <div style="background:#f1f5f9;border-radius:12px;padding:24px;text-align:center;margin-bottom:24px">
                    <span style="font-size:40px;font-weight:700;letter-spacing:12px;color:#0f172a">
                      {html_escape(codigo)}
                    </span>
                  </div>
                  <p style="color:#94a3b8;font-size:13px">
                    Si no solicitaste este código, ignora este mensaje.
                  </p>
                </div>
            """,
        })
    except Exception as exc:
        logger.error("Error enviando código a %s: %s", email, exc)


def validar_codigo_verificacion(email: str, codigo: str) -> None:
    """
    Verifica que el código OTP sea correcto, no haya expirado y no haya sido usado.
    Lo marca como usado si es válido. Incrementa intentos_fallidos si es incorrecto
    y bloquea el código tras OTP_MAX_INTENTOS intentos fallidos.

    Usa select_for_update() para serializar el acceso concurrente y evitar
    race conditions en el conteo de intentos fallidos.

    Raises:
        CodigoInvalidoError: Si el código no existe, expiró o ya fue usado.
        CodigoBloqueadoError: Si el código fue bloqueado por demasiados intentos.
    """
    # Normalizar email para que coincida con el guardado al solicitar
    email = email.strip().lower()

    with transaction.atomic():
        # select_for_update serializa el acceso: evita race condition en intentos_fallidos
        registro = (
            CodigoVerificacion.objects
            .select_for_update()
            .filter(email=email, usado=False)
            .order_by("-creado_en")
            .first()
        )

        if not registro:
            raise CodigoInvalidoError("El código es incorrecto o ha expirado.")

        # Verificar si ya está bloqueado por intentos
        max_intentos = django_settings.OTP_MAX_INTENTOS
        if registro.intentos_fallidos >= max_intentos:
            raise CodigoBloqueadoError(
                "El código ha sido bloqueado por demasiados intentos. "
                "Solicita un nuevo código."
            )

        # Verificar expiración
        if not registro.is_valid():
            raise CodigoInvalidoError("El código es incorrecto o ha expirado.")

        # Verificar que el código coincide
        if registro.codigo != codigo:
            # Calcular el nuevo valor localmente para evitar refresh_from_db
            nuevos_intentos = registro.intentos_fallidos + 1
            CodigoVerificacion.objects.filter(pk=registro.pk).update(
                intentos_fallidos=F("intentos_fallidos") + 1
            )
            restantes = max_intentos - nuevos_intentos
            if restantes <= 0:
                raise CodigoBloqueadoError(
                    "El código ha sido bloqueado por demasiados intentos. "
                    "Solicita un nuevo código."
                )
            raise CodigoInvalidoError(
                f"El código es incorrecto. Te quedan {restantes} intento(s)."
            )

        registro.usado = True
        registro.save(update_fields=["usado"])

    logger.info("Código verificado correctamente para %s", email)


def email_esta_verificado(email: str) -> bool:
    """
    Devuelve True si existe un código usado recientemente para este email.
    La ventana de validez es configurable via settings.OTP_VERIFICACION_VENTANA_MINUTOS
    (default: 30 min). Usado por el endpoint de registro para confirmar
    que el email fue verificado antes de crear la cuenta.
    """
    # Normalizar para que coincida con el email guardado al solicitar el código
    email = email.strip().lower()
    ventana = timedelta(minutes=django_settings.OTP_VERIFICACION_VENTANA_MINUTOS)
    desde = timezone.now() - ventana
    return CodigoVerificacion.objects.filter(
        email=email,
        usado=True,
        creado_en__gte=desde,
    ).exists()


# ─── Servicio de registro ─────────────────────────────────────────────────────

def registrar_clinica(data: RegistroClinicaInput) -> RegistroClinicaResult:
    """
    Registra una nueva clínica creando un usuario con rol admin.

    Raises:
        CamposObligatoriosError: Si nombre_clinica, nombre_admin o email están vacíos.
        EmailYaRegistradoError: Si el email ya está en uso.
        PasswordDemasiadoCortaError: Si la contraseña tiene menos de 8 caracteres.

    Returns:
        RegistroClinicaResult con el usuario creado y los tokens JWT.
    """
    # Validaciones de dominio
    if not all([data.nombre_clinica, data.nombre_admin, data.email]):
        raise CamposObligatoriosError("Todos los campos son obligatorios.")

    # Normalizar email a lowercase para consistencia en la DB
    email = data.email.strip().lower()

    try:
        validate_email(email)
    except DjangoValidationError:
        raise EmailFormatoInvalidoError("El correo electrónico no tiene un formato válido.")

    if _email_en_uso(email):
        raise EmailYaRegistradoError("Este correo ya está en uso")

    if len(data.password) < 8:
        raise PasswordDemasiadoCortaError("La contraseña debe tener al menos 8 caracteres")

    # Verificar que el email fue verificado con código OTP
    if not email_esta_verificado(email):
        raise CamposObligatoriosError("Debes verificar tu correo electrónico antes de registrarte.")

    # Crear usuario, clínica y perfil — y generar tokens — en una transacción atómica
    with transaction.atomic():
        clinica = Clinica.objects.create(
            nombre=data.nombre_clinica,
            email_admin=email,
        )
        user = User.objects.create_user(
            username=email,
            email=email,
            password=data.password,
            first_name=data.nombre_admin,  # nombre del administrador
            # last_name se deja vacío — el nombre de la clínica vive en Clinica.nombre
        )
        PerfilUsuario.objects.create(
            user=user,
            clinica=clinica,
            rol=PerfilUsuario.Rol.ADMIN,
        )
        # Generar tokens dentro del atomic para que un fallo aquí revierta todo
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

    logger.info("Nueva clínica registrada: email=%s clinica='%s'", email, data.nombre_clinica)

    # Correo de bienvenida — el error no bloquea el registro
    _enviar_correo_bienvenida(
        email=email,
        nombre_admin=data.nombre_admin,
        nombre_clinica=data.nombre_clinica,
    )

    return RegistroClinicaResult(
        user=user,
        clinica=clinica,
        access_token=access_token,
        refresh_token=refresh_token,
    )


def _enviar_correo_bienvenida(email: str, nombre_admin: str, nombre_clinica: str) -> None:
    """Envía el correo de bienvenida usando Resend. Los errores se loguean pero no propagan."""
    api_key = django_settings.RESEND_API_KEY
    from_email = django_settings.EMAIL_FROM

    if not api_key:
        logger.warning("RESEND_API_KEY no configurada — correo de bienvenida no enviado a %s", email)
        return

    resend.api_key = api_key

    try:
        resend.Emails.send({
            "from": from_email,
            "to": [email],
            "subject": "Bienvenido a Veterinaria Scarlet",
            "html": f"""
                <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px">
                  <h2 style="color:#16a34a;margin-bottom:8px">Veterinaria Scarlet</h2>
                  <p style="color:#475569;margin-bottom:16px">
                    Hola <strong>{html_escape(nombre_admin)}</strong>,
                  </p>
                  <p style="color:#475569;margin-bottom:16px">
                    Tu clínica <strong>{html_escape(nombre_clinica)}</strong> ha sido registrada exitosamente.
                  </p>
                  <p style="color:#475569;margin-bottom:24px">
                    Ya puedes iniciar sesión con tu correo: <strong>{html_escape(email)}</strong>
                  </p>
                  <p style="color:#94a3b8;font-size:13px">
                    Equipo Veterinaria Scarlet
                  </p>
                </div>
            """,
        })
        logger.info("Correo de bienvenida enviado a %s", email)
    except Exception as exc:
        logger.warning("No se pudo enviar el correo de bienvenida a %s: %s", email, exc)


# ─── Servicio de búsqueda de pacientes ───────────────────────────────────────

def buscar_pacientes(search: str = "", clinica=None) -> QuerySet:
    """
    Retorna un QuerySet de pacientes activos con sus relaciones precargadas.

    Args:
        search: Término de búsqueda (máx. 100 chars). Filtra por nombre del
                paciente, nombre del tutor o nombre de la especie.
        clinica: Si se proporciona, filtra los pacientes por clínica.

    Returns:
        QuerySet de Paciente con select_related aplicado.
    """
    queryset = (
        Paciente.objects  # ActiveManager ya filtra eliminado_en__isnull=True
        .select_related("tutor", "especie", "sexo")
        .filter(
            tutor__eliminado_en__isnull=True,
            especie__eliminado_en__isnull=True,
        )
    )

    if clinica is not None:
        queryset = queryset.filter(clinica=clinica)

    # Limitar a 100 chars para evitar queries costosas
    term = search.strip()[:100]
    if term:
        queryset = queryset.filter(
            Q(nombre__icontains=term)
            | Q(tutor__nombre__icontains=term)
            | Q(especie__nombre__icontains=term)
        )
        logger.debug("Búsqueda de pacientes: term='%s'", term)

    return queryset


# ─── Servicio de gestión de veterinarios ─────────────────────────────────────

@dataclass
class CrearVeterinarioInput:
    nombre: str
    email: str
    password: str


@dataclass
class VeterinarioResult:
    id: int
    nombre: str
    email: str
    rol: str


class VeterinarioNoEncontradoError(ValueError):
    """El veterinario con el id dado no existe."""


class NoSePuedeEliminarAdminError(ValueError):
    """No se puede eliminar un usuario con rol admin."""


def crear_veterinario(data: CrearVeterinarioInput, clinica: "Clinica") -> VeterinarioResult:
    """
    Crea un usuario con rol veterinario asociado a la clínica indicada.

    Raises:
        CamposObligatoriosError: Si nombre o email están vacíos.
        EmailYaRegistradoError: Si el email ya está en uso.
        PasswordDemasiadoCortaError: Si la contraseña tiene menos de 8 caracteres.

    Returns:
        VeterinarioResult con los datos del usuario creado.
    """
    if not all([data.nombre, data.email]):
        raise CamposObligatoriosError("Nombre y correo son obligatorios.")

    # Normalizar email a lowercase para consistencia en la DB
    email = data.email.strip().lower()

    try:
        validate_email(email)
    except DjangoValidationError:
        raise EmailFormatoInvalidoError("El correo electrónico no tiene un formato válido.")

    if _email_en_uso(email):
        raise EmailYaRegistradoError("Este correo ya está en uso.")

    if len(data.password) < 8:
        raise PasswordDemasiadoCortaError("La contraseña debe tener al menos 8 caracteres.")

    with transaction.atomic():
        user = User.objects.create_user(
            username=email,
            email=email,
            password=data.password,
            first_name=data.nombre,
        )
        PerfilUsuario.objects.create(
            user=user,
            clinica=clinica,
            rol=PerfilUsuario.Rol.VETERINARIO,
        )

    logger.info("Veterinario creado: email=%s nombre='%s' clinica=%s", email, data.nombre, clinica.id)
    return VeterinarioResult(
        id=user.id,
        nombre=user.first_name,
        email=user.email,
        rol="veterinario",
    )


def listar_veterinarios(clinica: "Clinica") -> list[VeterinarioResult]:
    """
    Retorna todos los veterinarios activos de la clínica indicada.
    """
    perfiles = (
        PerfilUsuario.objects
        .filter(clinica=clinica, rol=PerfilUsuario.Rol.VETERINARIO, user__is_active=True)
        .select_related("user")
        .order_by("user__first_name", "user__email")
    )
    return [
        VeterinarioResult(id=p.user.id, nombre=p.user.first_name, email=p.user.email, rol="veterinario")
        for p in perfiles
    ]


@dataclass
class EditarVeterinarioInput:
    nombre: str | None
    email: str | None
    password: str | None


def editar_veterinario(user_id: int, data: EditarVeterinarioInput, clinica: "Clinica") -> VeterinarioResult:
    """
    Actualiza nombre, email y/o contraseña de un veterinario de la clínica indicada.

    Raises:
        VeterinarioNoEncontradoError: Si el usuario no existe o no pertenece a la clínica.
        NoSePuedeEliminarAdminError: Si el usuario es admin o superusuario.
        EmailYaRegistradoError: Si el nuevo email ya está en uso por otro usuario.
        PasswordDemasiadoCortaError: Si la nueva contraseña tiene menos de 8 caracteres.
    """
    # Una sola query con select_related en lugar de dos queries separadas
    try:
        perfil = PerfilUsuario.objects.select_related("user").get(
            user_id=user_id,
            clinica=clinica,
            user__is_active=True,
        )
    except PerfilUsuario.DoesNotExist:
        raise VeterinarioNoEncontradoError(f"No existe un usuario con id={user_id}.")

    user = perfil.user

    if user.is_superuser or perfil.rol == PerfilUsuario.Rol.ADMIN:
        raise NoSePuedeEliminarAdminError("No se puede editar un usuario administrador.")

    if data.email and data.email != user.email:
        nuevo_email = data.email.strip().lower()
        try:
            validate_email(nuevo_email)
        except DjangoValidationError:
            raise EmailFormatoInvalidoError("El correo electrónico no tiene un formato válido.")
        if _email_en_uso(nuevo_email, exclude_pk=user_id):
            raise EmailYaRegistradoError("Este correo ya está en uso.")
    else:
        nuevo_email = None

    if data.password is not None and len(data.password) < 8:
        raise PasswordDemasiadoCortaError("La contraseña debe tener al menos 8 caracteres.")

    update_fields = []
    if data.nombre is not None:
        user.first_name = data.nombre
        update_fields.append("first_name")
    if nuevo_email:
        user.email = nuevo_email
        user.username = nuevo_email
        update_fields.extend(["email", "username"])
    if data.password:
        user.set_password(data.password)
        update_fields.append("password")

    if update_fields:
        user.save(update_fields=update_fields)
        logger.info("Veterinario editado: id=%s campos=%s", user.id, update_fields)

    return VeterinarioResult(id=user.id, nombre=user.first_name, email=user.email, rol="veterinario")


def eliminar_veterinario(user_id: int, clinica: "Clinica") -> None:
    """
    Desactiva (soft-disable) un usuario veterinario de la clínica indicada.

    Raises:
        VeterinarioNoEncontradoError: Si el usuario no existe o no pertenece a la clínica.
        NoSePuedeEliminarAdminError: Si el usuario es admin o superusuario.
    """
    # Una sola query con select_related en lugar de dos queries separadas
    try:
        perfil = PerfilUsuario.objects.select_related("user").get(
            user_id=user_id,
            clinica=clinica,
        )
    except PerfilUsuario.DoesNotExist:
        raise VeterinarioNoEncontradoError(f"No existe un usuario con id={user_id}.")

    user = perfil.user

    if user.is_superuser or perfil.rol == PerfilUsuario.Rol.ADMIN:
        raise NoSePuedeEliminarAdminError("No se puede eliminar un usuario administrador.")

    user.is_active = False
    user.save(update_fields=["is_active"])
    logger.info("Veterinario desactivado: id=%s email=%s", user.id, user.email)


def sincronizar_email_admin_clinica(clinica: "Clinica", nuevo_email: str) -> None:
    """
    Sincroniza User.email y User.username del administrador de la clínica
    cuando se actualiza Clinica.email_admin vía PATCH /clinica/.

    Si el usuario admin no se encuentra (caso raro), loguea un warning
    pero no lanza excepción para no bloquear la actualización de la clínica.
    """
    nuevo_email = nuevo_email.strip().lower()
    try:
        perfil = (
            PerfilUsuario.objects
            .select_related("user")
            .get(clinica=clinica, rol=PerfilUsuario.Rol.ADMIN)
        )
    except PerfilUsuario.DoesNotExist:
        logger.warning(
            "No se encontró perfil admin para clinica_id=%s al sincronizar email", clinica.id
        )
        return
    except PerfilUsuario.MultipleObjectsReturned:
        logger.warning(
            "Múltiples admins en clinica_id=%s — no se sincroniza User.email", clinica.id
        )
        return

    user = perfil.user
    if user.email == nuevo_email:
        return  # Nada que sincronizar

    user.email = nuevo_email
    user.username = nuevo_email
    user.save(update_fields=["email", "username"])
    logger.info(
        "User.email sincronizado con Clinica.email_admin: user_id=%s email=%s",
        user.id,
        nuevo_email,
    )


def obtener_alertas_clinicas(
    clinica: "Clinica",
    dias_anticipacion: int = 30,
) -> AlertasClinicaResult:
    """
    Calcula las alertas clínicas activas: vacunas vencidas, vacunas próximas
    y tratamientos activos, filtradas por la clínica indicada.

    Args:
        clinica: La clínica cuyas alertas se calculan.
        dias_anticipacion: Días hacia adelante para considerar vacunas "próximas".
                           Por defecto 30 días.

    Returns:
        AlertasClinicaResult con los querysets correspondientes.
    """
    hoy = date.today()
    limite = hoy + timedelta(days=dias_anticipacion)

    base_vacuna_qs = (
        Vacuna.objects
        .select_related("paciente")
        .filter(
            clinica=clinica,
            paciente__eliminado_en__isnull=True,
            proxima_dosis__isnull=False,
        )
    )

    vacunas_vencidas = (
        base_vacuna_qs
        .filter(proxima_dosis__lt=hoy)
        .order_by("proxima_dosis")
    )

    vacunas_proximas = (
        base_vacuna_qs
        .filter(proxima_dosis__gte=hoy, proxima_dosis__lte=limite)
        .order_by("proxima_dosis")
    )

    tratamientos_activos = (
        Tratamiento.objects
        .select_related("paciente")
        .filter(
            clinica=clinica,
            paciente__eliminado_en__isnull=True,
            fecha_inicio__lte=hoy,
        )
        .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy))
        .order_by("fecha_fin", "-fecha_inicio")
    )

    logger.debug("Alertas calculadas para clinica_id=%s", clinica.id)

    return AlertasClinicaResult(
        fecha_revision=hoy,
        limite_revision=limite,
        vacunas_vencidas=vacunas_vencidas,
        vacunas_proximas=vacunas_proximas,
        tratamientos_activos=tratamientos_activos,
    )
