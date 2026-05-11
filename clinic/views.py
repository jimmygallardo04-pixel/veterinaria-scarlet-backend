"""
Vistas y ViewSets de la API de Veterinaria Scarlet.

Las vistas son responsables únicamente de:
  - Parsear la request HTTP
  - Delegar la lógica de negocio a la capa de servicios (services.py)
  - Serializar y devolver la respuesta HTTP

La lógica de negocio (alertas, búsqueda, registro) vive en services.py.
"""

import logging
import hmac

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Prefetch, Q, prefetch_related_objects

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    ArchivoDocumento,
    Cita,
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
from .serializers import (
    ArchivoDocumentoSerializer,
    CitaSerializer,
    ClinicaEditSerializer,
    EspecieSerializer,
    FichaClinicaDetalleSerializer,
    FichaClinicaSerializer,
    PacienteSerializer,
    SexoPacienteSerializer,
    TipoArchivoDocumentoSerializer,
    TratamientoSerializer,
    TutorSerializer,
    VacunaSerializer,
)
from .services import (
    AlertasClinicaResult,
    CamposObligatoriosError,
    CodigoBloqueadoError,
    CodigoInvalidoError,
    CrearVeterinarioInput,
    EditarVeterinarioInput,
    EmailYaRegistradoError,
    NoSePuedeEliminarAdminError,
    PasswordDemasiadoCortaError,
    RegistroClinicaInput,
    VeterinarioNoEncontradoError,
    buscar_pacientes,
    crear_veterinario,
    editar_veterinario,
    eliminar_veterinario,
    listar_veterinarios,
    obtener_alertas_clinicas,
    registrar_clinica,
    solicitar_codigo_verificacion,
    validar_codigo_verificacion,
)

logger = logging.getLogger(__name__)


# ─── Base ViewSet ─────────────────────────────────────────────────────────────

class SoftDeleteModelViewSet(viewsets.ModelViewSet):
    """ModelViewSet que realiza soft-delete en lugar de borrado físico."""

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete()
        logger.info(
            "Soft-delete: modelo=%s id=%s usuario=%s",
            instance.__class__.__name__,
            instance.pk,
            request.user.username,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Permisos por rol ─────────────────────────────────────────────────────────

def es_admin(user) -> bool:
    """Devuelve True si el usuario es superusuario o tiene rol 'admin' en su PerfilUsuario."""
    if user.is_superuser:
        return True
    try:
        return user.perfil.rol == PerfilUsuario.Rol.ADMIN
    except PerfilUsuario.DoesNotExist:
        return False


class EsAdminOSoloLectura(BasePermission):
    """Admins pueden todo; veterinarios solo lectura (GET, HEAD, OPTIONS)."""
    message = "Se requiere rol de administrador para modificar."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return es_admin(request.user)


# ─── Throttles ────────────────────────────────────────────────────────────────

class LoginRateThrottle(AnonRateThrottle):
    """Máximo 5 intentos de login por minuto por IP."""
    scope = "login"

    def get_rate(self):
        try:
            return super().get_rate()
        except Exception:
            return None  # Sin límite en entornos de test


class RegistroRateThrottle(AnonRateThrottle):
    """Máximo 10 registros por hora por IP."""
    scope = "registro"

    def get_rate(self):
        try:
            return super().get_rate()
        except Exception:
            return None  # Sin límite en entornos de test


class ValidacionCodigoThrottle(AnonRateThrottle):
    """Máximo 5 validaciones de código por hora por IP."""
    scope = "validacion_codigo"

    def get_rate(self):
        try:
            return super().get_rate()
        except Exception:
            return None  # Sin límite en entornos de test


class FlexibleTokenSerializer(TokenObtainPairSerializer):
    """
    Serializer de login que acepta email o username de Django.

    Se eliminó la búsqueda por first_name para evitar enumeración de cuentas
    a través del nombre de la clínica (que es público).
    """

    def validate(self, attrs):
        identifier = attrs.get("username", "").strip()

        # Una sola query: busca por username exacto o por email
        user = User.objects.filter(
            Q(username=identifier) | Q(email=identifier),
            is_active=True,
        ).first()

        if user:
            # Sustituir el identificador por el username real para que
            # TokenObtainPairSerializer pueda autenticar correctamente
            attrs["username"] = user.username

        return super().validate(attrs)


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Vista de login con rate limiting: 5 intentos/minuto por IP."""
    throttle_classes = [LoginRateThrottle]
    serializer_class = FlexibleTokenSerializer


# ─── Mixin: filtrado por ?paciente= ──────────────────────────────────────────

class PacienteFilterMixin:
    """
    Mixin que añade filtrado por ?paciente={id} a cualquier ViewSet.
    Requiere que el queryset tenga un campo `paciente_id`.
    """

    def _apply_paciente_filter(self, queryset):
        paciente_id = self.request.query_params.get("paciente")
        if paciente_id is not None:
            # Validar que sea un entero positivo para evitar valores malformados
            try:
                paciente_id_int = int(paciente_id)
                if paciente_id_int <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                return queryset.none()
            queryset = queryset.filter(paciente_id=paciente_id_int)
        return queryset


# ─── Mixin: filtrado por tenant (clínica) ────────────────────────────────────

class TenantQuerysetMixin:
    """
    Filtra automáticamente el queryset por la clínica del usuario autenticado.

    Requiere que el modelo tenga un campo `clinica_id`.
    Si el usuario no tiene PerfilUsuario, devuelve HTTP 403.
    Si el usuario es superusuario, omite el filtro de tenant.
    """

    def get_clinica(self):
        if self.request.user.is_superuser:
            return None
        # Cachear en la instancia del ViewSet para evitar queries repetidas en la misma
        # request. Seguro porque Django instancia un ViewSet nuevo por cada request.
        if not hasattr(self, "_clinica_cache"):
            try:
                self._clinica_cache = self.request.user.perfil.clinica
            except (AttributeError, PerfilUsuario.DoesNotExist):
                raise PermissionDenied(
                    "Tu cuenta no está asociada a ninguna clínica."
                )
        return self._clinica_cache

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_superuser:
            return qs  # Sin filtro de tenant para superusuarios
        clinica = self.get_clinica()
        return qs.filter(clinica=clinica)

    def perform_create(self, serializer):
        serializer.save(clinica=self.get_clinica())


# ─── Endpoint /me/ ───────────────────────────────────────────────────────────

@extend_schema(
    summary="Usuario autenticado",
    description="Devuelve los datos del usuario autenticado con su rol y datos de clínica.",
    tags=["Auth"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    """Devuelve el usuario autenticado con su rol y datos de clínica."""
    # Cargar perfil+clinica solo si no están ya en el caché del objeto user
    cache_key = "_prefetched_objects_cache"
    already_cached = (
        hasattr(request.user, cache_key)
        and "perfil" in getattr(request.user, cache_key, {})
    )
    if not already_cached:
        prefetch_related_objects([request.user], "perfil__clinica")
    user = request.user
    try:
        perfil = user.perfil
        clinica_id = perfil.clinica_id
        clinica_nombre = perfil.clinica.nombre
        rol = perfil.rol
    except (AttributeError, PerfilUsuario.DoesNotExist):
        clinica_id = None
        clinica_nombre = None
        rol = "superusuario" if user.is_superuser else None

    return Response({
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_superuser": user.is_superuser,
        "rol": rol,
        "clinica_id": clinica_id,
        "clinica_nombre": clinica_nombre,
    })


# ─── ViewSets de catálogos (sin paginación, con caché) ───────────────────────
# Los catálogos son datos casi estáticos. Se cachean para reducir queries.
# La caché se invalida automáticamente al crear/actualizar/eliminar un registro.

class _CachedCatalogMixin:
    """
    Mixin que invalida la caché del catálogo al escribir.
    Subclases deben definir `_cache_key: str`.
    """
    _cache_key: str = ""

    def _invalidate_cache(self) -> None:
        if self._cache_key:
            cache.delete(self._cache_key)
            logger.debug("Caché invalidada: key=%s", self._cache_key)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._invalidate_cache()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._invalidate_cache()

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        self._invalidate_cache()
        return response


@extend_schema_view(
    list=extend_schema(summary="Listar especies", tags=["Catálogos"]),
    create=extend_schema(summary="Crear especie", tags=["Catálogos"]),
    retrieve=extend_schema(summary="Obtener especie", tags=["Catálogos"]),
    update=extend_schema(summary="Actualizar especie", tags=["Catálogos"]),
    partial_update=extend_schema(summary="Actualizar especie parcialmente", tags=["Catálogos"]),
    destroy=extend_schema(summary="Eliminar especie", tags=["Catálogos"]),
)
class EspecieViewSet(_CachedCatalogMixin, TenantQuerysetMixin, SoftDeleteModelViewSet):
    serializer_class = EspecieSerializer
    permission_classes = [EsAdminOSoloLectura]
    pagination_class = None
    queryset = Especie.objects.all()

    @property
    def _cache_key(self):
        clinica = self.get_clinica()
        clinica_id = clinica.id if clinica else "all"
        return f"catalogo:especies:{clinica_id}"


@extend_schema_view(
    list=extend_schema(summary="Listar sexos de paciente", tags=["Catálogos"]),
    create=extend_schema(summary="Crear sexo", tags=["Catálogos"]),
    retrieve=extend_schema(summary="Obtener sexo", tags=["Catálogos"]),
    update=extend_schema(summary="Actualizar sexo", tags=["Catálogos"]),
    partial_update=extend_schema(summary="Actualizar sexo parcialmente", tags=["Catálogos"]),
    destroy=extend_schema(summary="Eliminar sexo", tags=["Catálogos"]),
)
class SexoPacienteViewSet(_CachedCatalogMixin, TenantQuerysetMixin, SoftDeleteModelViewSet):
    serializer_class = SexoPacienteSerializer
    permission_classes = [EsAdminOSoloLectura]
    pagination_class = None
    queryset = SexoPaciente.objects.all()

    @property
    def _cache_key(self):
        clinica = self.get_clinica()
        clinica_id = clinica.id if clinica else "all"
        return f"catalogo:sexos:{clinica_id}"


@extend_schema_view(
    list=extend_schema(summary="Listar tipos de archivo", tags=["Catálogos"]),
    create=extend_schema(summary="Crear tipo de archivo", tags=["Catálogos"]),
    retrieve=extend_schema(summary="Obtener tipo de archivo", tags=["Catálogos"]),
    update=extend_schema(summary="Actualizar tipo de archivo", tags=["Catálogos"]),
    partial_update=extend_schema(summary="Actualizar tipo de archivo parcialmente", tags=["Catálogos"]),
    destroy=extend_schema(summary="Eliminar tipo de archivo", tags=["Catálogos"]),
)
class TipoArchivoDocumentoViewSet(_CachedCatalogMixin, TenantQuerysetMixin, SoftDeleteModelViewSet):
    serializer_class = TipoArchivoDocumentoSerializer
    permission_classes = [EsAdminOSoloLectura]
    pagination_class = None
    queryset = TipoArchivoDocumento.objects.all()

    @property
    def _cache_key(self):
        clinica = self.get_clinica()
        clinica_id = clinica.id if clinica else "all"
        return f"catalogo:tipos_archivo:{clinica_id}"


# ─── ViewSets principales ─────────────────────────────────────────────────────

@extend_schema_view(
    list=extend_schema(summary="Listar tutores", tags=["Tutores"]),
    create=extend_schema(summary="Crear tutor", tags=["Tutores"]),
    retrieve=extend_schema(summary="Obtener tutor", tags=["Tutores"]),
    update=extend_schema(summary="Actualizar tutor", tags=["Tutores"]),
    partial_update=extend_schema(summary="Actualizar tutor parcialmente", tags=["Tutores"]),
    destroy=extend_schema(summary="Eliminar tutor", tags=["Tutores"]),
)
class TutorViewSet(TenantQuerysetMixin, SoftDeleteModelViewSet):
    serializer_class = TutorSerializer
    permission_classes = [IsAuthenticated]
    queryset = Tutor.objects.all()


@extend_schema_view(
    list=extend_schema(
        summary="Listar pacientes",
        tags=["Pacientes"],
        parameters=[
            OpenApiParameter(
                name="search",
                description="Busca por nombre del paciente, tutor o especie.",
                required=False,
                type=str,
            )
        ],
    ),
    create=extend_schema(summary="Crear paciente", tags=["Pacientes"]),
    retrieve=extend_schema(summary="Obtener paciente", tags=["Pacientes"]),
    update=extend_schema(summary="Actualizar paciente", tags=["Pacientes"]),
    partial_update=extend_schema(summary="Actualizar paciente parcialmente", tags=["Pacientes"]),
    destroy=extend_schema(summary="Eliminar paciente", tags=["Pacientes"]),
)
class PacienteViewSet(TenantQuerysetMixin, SoftDeleteModelViewSet):
    serializer_class = PacienteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        search = self.request.query_params.get("search", "")
        clinica = self.get_clinica()
        return buscar_pacientes(search=search, clinica=clinica)


@extend_schema_view(
    list=extend_schema(summary="Listar fichas clínicas", tags=["Fichas Clínicas"]),
    create=extend_schema(summary="Crear ficha clínica", tags=["Fichas Clínicas"]),
    retrieve=extend_schema(summary="Obtener ficha clínica (detalle completo)", tags=["Fichas Clínicas"]),
    update=extend_schema(summary="Actualizar ficha clínica", tags=["Fichas Clínicas"]),
    partial_update=extend_schema(summary="Actualizar ficha clínica parcialmente", tags=["Fichas Clínicas"]),
    destroy=extend_schema(summary="Eliminar ficha clínica", tags=["Fichas Clínicas"]),
)
class FichaClinicaViewSet(TenantQuerysetMixin, PacienteFilterMixin, SoftDeleteModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return FichaClinicaDetalleSerializer
        return FichaClinicaSerializer

    def get_queryset(self):
        clinica = self.get_clinica()
        queryset = FichaClinica.objects.select_related(
            "paciente", "paciente__tutor", "paciente__especie", "paciente__sexo"
        )
        # El prefetch pesado solo es necesario en retrieve (detalle completo)
        if self.action == "retrieve":
            queryset = queryset.prefetch_related(
                Prefetch("paciente__vacunas", queryset=Vacuna.objects.filter(eliminado_en__isnull=True)),
                Prefetch("paciente__tratamientos", queryset=Tratamiento.objects.filter(eliminado_en__isnull=True)),
                Prefetch("paciente__archivos", queryset=ArchivoDocumento.objects.filter(eliminado_en__isnull=True)),
                Prefetch("paciente__fichas", queryset=FichaClinica.objects.filter(eliminado_en__isnull=True)),
            )
        queryset = queryset.filter(
            paciente__eliminado_en__isnull=True,
            paciente__tutor__eliminado_en__isnull=True,
        )
        if clinica is not None:
            queryset = queryset.filter(clinica=clinica)
        return self._apply_paciente_filter(queryset)


@extend_schema_view(
    list=extend_schema(summary="Listar citas", tags=["Citas"]),
    create=extend_schema(summary="Crear cita", tags=["Citas"]),
    retrieve=extend_schema(summary="Obtener cita", tags=["Citas"]),
    update=extend_schema(summary="Actualizar cita", tags=["Citas"]),
    partial_update=extend_schema(summary="Actualizar cita parcialmente", tags=["Citas"]),
    destroy=extend_schema(summary="Eliminar cita", tags=["Citas"]),
)
class CitaViewSet(TenantQuerysetMixin, PacienteFilterMixin, SoftDeleteModelViewSet):
    serializer_class = CitaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            Cita.objects
            .select_related("paciente", "tutor")
            .filter(
                paciente__eliminado_en__isnull=True,
                tutor__eliminado_en__isnull=True,
            )
        )
        return self._apply_paciente_filter(queryset)


@extend_schema_view(
    list=extend_schema(summary="Listar vacunas", tags=["Vacunas"]),
    create=extend_schema(summary="Registrar vacuna", tags=["Vacunas"]),
    retrieve=extend_schema(summary="Obtener vacuna", tags=["Vacunas"]),
    update=extend_schema(summary="Actualizar vacuna", tags=["Vacunas"]),
    partial_update=extend_schema(summary="Actualizar vacuna parcialmente", tags=["Vacunas"]),
    destroy=extend_schema(summary="Eliminar vacuna", tags=["Vacunas"]),
)
class VacunaViewSet(TenantQuerysetMixin, PacienteFilterMixin, SoftDeleteModelViewSet):
    serializer_class = VacunaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            Vacuna.objects
            .select_related("paciente")
            .filter(paciente__eliminado_en__isnull=True)
        )
        return self._apply_paciente_filter(queryset)


@extend_schema_view(
    list=extend_schema(summary="Listar tratamientos", tags=["Tratamientos"]),
    create=extend_schema(summary="Crear tratamiento", tags=["Tratamientos"]),
    retrieve=extend_schema(summary="Obtener tratamiento", tags=["Tratamientos"]),
    update=extend_schema(summary="Actualizar tratamiento", tags=["Tratamientos"]),
    partial_update=extend_schema(summary="Actualizar tratamiento parcialmente", tags=["Tratamientos"]),
    destroy=extend_schema(summary="Eliminar tratamiento", tags=["Tratamientos"]),
)
class TratamientoViewSet(TenantQuerysetMixin, PacienteFilterMixin, SoftDeleteModelViewSet):
    serializer_class = TratamientoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            Tratamiento.objects
            .select_related("paciente")
            .filter(paciente__eliminado_en__isnull=True)
        )
        return self._apply_paciente_filter(queryset)


@extend_schema_view(
    list=extend_schema(summary="Listar archivos y documentos", tags=["Archivos"]),
    create=extend_schema(summary="Subir archivo", tags=["Archivos"]),
    retrieve=extend_schema(summary="Obtener archivo", tags=["Archivos"]),
    update=extend_schema(summary="Actualizar archivo", tags=["Archivos"]),
    partial_update=extend_schema(summary="Actualizar archivo parcialmente", tags=["Archivos"]),
    destroy=extend_schema(summary="Eliminar archivo", tags=["Archivos"]),
)
class ArchivoDocumentoViewSet(TenantQuerysetMixin, PacienteFilterMixin, SoftDeleteModelViewSet):
    serializer_class = ArchivoDocumentoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            ArchivoDocumento.objects
            .select_related("paciente", "tipo")
            .filter(paciente__eliminado_en__isnull=True)
        )
        return self._apply_paciente_filter(queryset)


# ─── Endpoints de verificación de email ──────────────────────────────────────

@extend_schema(
    summary="Solicitar código de verificación",
    description="Envía un código OTP de 6 dígitos al email indicado. Expira en 15 minutos.",
    tags=["Auth"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegistroRateThrottle])
def solicitar_codigo_view(request):
    """POST { email, registro_secret_key } → envía código OTP al correo."""
    # Verificar la clave secreta de registro antes de enviar el OTP
    secret_key = settings.REGISTRO_SECRET_KEY
    if secret_key:
        provided_key = request.data.get("registro_secret_key", "")
        if not provided_key or not hmac.compare_digest(str(provided_key), str(secret_key)):
            return Response(
                {"detail": "Clave de registro incorrecta."},
                status=status.HTTP_403_FORBIDDEN,
            )

    email = request.data.get("email", "").strip()
    try:
        solicitar_codigo_verificacion(email)
    except CamposObligatoriosError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.error("Error enviando código a %s: %s", email, exc, exc_info=True)
        return Response(
            {"detail": "No se pudo enviar el código. Intenta nuevamente."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response({"detail": "Código enviado. Revisa tu correo."}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Validar código de verificación",
    description="Verifica el código OTP ingresado por el usuario.",
    tags=["Auth"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ValidacionCodigoThrottle])
def validar_codigo_view(request):
    """POST { email, codigo } → valida el código OTP."""
    email = request.data.get("email", "").strip()
    codigo = request.data.get("codigo", "").strip()
    try:
        validar_codigo_verificacion(email, codigo)
    except CodigoBloqueadoError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except CodigoInvalidoError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.error("Error validando código para %s: %s", email, exc, exc_info=True)
        return Response(
            {"detail": "Error interno. Intenta nuevamente."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response({"detail": "Correo verificado correctamente."}, status=status.HTTP_200_OK)


# ─── Endpoint /registro/ ─────────────────────────────────────────────────────

@extend_schema(
    summary="Registrar nueva clínica",
    description=(
        "Crea un usuario administrador para una nueva clínica. "
        "Devuelve tokens JWT listos para usar."
    ),
    tags=["Auth"],
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegistroRateThrottle])
def registro_clinica_view(request):
    """
    Registra una nueva clínica creando un usuario con rol admin.

    Body: { nombre_clinica, nombre_admin, email, password, registro_secret_key }
    Respuesta 201: { access, refresh, user: { id, username, email, first_name, rol } }
    """
    # Verificar la clave secreta de registro
    secret_key = settings.REGISTRO_SECRET_KEY
    if secret_key:
        provided_key = request.data.get("registro_secret_key", "")
        if not provided_key or not hmac.compare_digest(str(provided_key), str(secret_key)):
            return Response(
                {"detail": "Clave de registro incorrecta."},
                status=status.HTTP_403_FORBIDDEN,
            )
    data = RegistroClinicaInput(
        nombre_clinica=request.data.get("nombre_clinica", "").strip(),
        nombre_admin=request.data.get("nombre_admin", "").strip(),
        email=request.data.get("email", "").strip(),
        password=request.data.get("password", ""),
    )

    try:
        result = registrar_clinica(data)
    except CamposObligatoriosError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except EmailYaRegistradoError as exc:
        return Response({"email": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
    except PasswordDemasiadoCortaError as exc:
        return Response({"password": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.error("Error inesperado en registro_clinica_view: %s", exc, exc_info=True)
        return Response(
            {"detail": "Error interno al crear la cuenta. Intenta nuevamente."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "access": result.access_token,
            "refresh": result.refresh_token,
            "user": {
                "id": result.user.id,
                "email": result.user.email,
                "first_name": result.user.first_name,
                "rol": "admin",
                "clinica_id": result.clinica.id,
                "clinica_nombre": result.clinica.nombre,
            },
        },
        status=status.HTTP_201_CREATED,
    )


# ─── Endpoint /clinica/ ──────────────────────────────────────────────────────

@extend_schema(
    summary="Ver y editar datos de la clínica",
    description=(
        "GET devuelve los datos de la clínica del usuario autenticado. "
        "PATCH permite al administrador editar nombre y email_admin."
    ),
    tags=["Clínica"],
)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def clinica_view(request):
    """
    GET  → devuelve los datos de la clínica del usuario autenticado.
    PATCH → edita nombre y/o email_admin. Solo admins.
    """
    try:
        clinica = request.user.perfil.clinica
    except (AttributeError, PerfilUsuario.DoesNotExist):
        return Response(
            {"detail": "Tu cuenta no está asociada a ninguna clínica."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        serializer = ClinicaEditSerializer(clinica)
        return Response(serializer.data)

    # PATCH — solo admins
    if not es_admin(request.user):
        return Response(
            {"detail": "Se requiere rol de administrador para modificar los datos de la clínica."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = ClinicaEditSerializer(clinica, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save()
    logger.info(
        "Datos de clínica actualizados: clinica_id=%s usuario=%s campos=%s",
        clinica.id,
        request.user.username,
        list(request.data.keys()),
    )
    return Response(serializer.data)


# ─── Endpoint /veterinarios/ ─────────────────────────────────────────────────

@extend_schema(
    summary="Gestión de veterinarios",
    description="Lista, crea y elimina usuarios con rol veterinario. Solo accesible por admins.",
    tags=["Equipo"],
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def veterinarios_view(request):
    """
    GET  → lista todos los veterinarios activos.
    POST → crea un nuevo veterinario. Body: { nombre, email, password }
    """
    if not es_admin(request.user):
        return Response(
            {"detail": "Se requiere rol de administrador."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        clinica = request.user.perfil.clinica
    except (AttributeError, PerfilUsuario.DoesNotExist):
        return Response(
            {"detail": "Tu cuenta no está asociada a ninguna clínica."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        veterinarios = listar_veterinarios(clinica)
        return Response([
            {"id": v.id, "nombre": v.nombre, "email": v.email, "rol": v.rol}
            for v in veterinarios
        ])

    # POST — crear veterinario
    data = CrearVeterinarioInput(
        nombre=request.data.get("nombre", "").strip(),
        email=request.data.get("email", "").strip(),
        password=request.data.get("password", ""),
    )

    try:
        result = crear_veterinario(data, clinica)
    except CamposObligatoriosError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except EmailYaRegistradoError as exc:
        return Response({"email": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
    except PasswordDemasiadoCortaError as exc:
        return Response({"password": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.error("Error inesperado creando veterinario: %s", exc, exc_info=True)
        return Response(
            {"detail": "Error interno. Intenta nuevamente."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {"id": result.id, "nombre": result.nombre, "email": result.email, "rol": result.rol},
        status=status.HTTP_201_CREATED,
    )


@extend_schema(
    summary="Editar o eliminar veterinario",
    description="PATCH edita nombre/email/contraseña. DELETE desactiva la cuenta. Solo admins.",
    tags=["Equipo"],
)
@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def veterinario_detail_view(request, pk: int):
    """
    PATCH → edita nombre, email y/o contraseña del veterinario.
    DELETE → desactiva el veterinario con el id dado.
    """
    if not es_admin(request.user):
        return Response(
            {"detail": "Se requiere rol de administrador."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        clinica = request.user.perfil.clinica
    except (AttributeError, PerfilUsuario.DoesNotExist):
        return Response(
            {"detail": "Tu cuenta no está asociada a ninguna clínica."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "PATCH":
        data = EditarVeterinarioInput(
            nombre=request.data.get("nombre", "").strip() or None,
            email=request.data.get("email", "").strip() or None,
            password=request.data.get("password") or None,
        )
        try:
            result = editar_veterinario(pk, data, clinica)
        except VeterinarioNoEncontradoError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except NoSePuedeEliminarAdminError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except EmailYaRegistradoError as exc:
            return Response({"email": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        except PasswordDemasiadoCortaError as exc:
            return Response({"password": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error("Error editando veterinario id=%s: %s", pk, exc, exc_info=True)
            return Response({"detail": "Error interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {"id": result.id, "nombre": result.nombre, "email": result.email, "rol": result.rol}
        )

    # DELETE
    try:
        eliminar_veterinario(pk, clinica)
    except VeterinarioNoEncontradoError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except NoSePuedeEliminarAdminError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.error("Error inesperado eliminando veterinario id=%s: %s", pk, exc, exc_info=True)
        return Response({"detail": "Error interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Endpoint /alertas/ ──────────────────────────────────────────────────────

@extend_schema_view(
    list=extend_schema(
        summary="Alertas clínicas",
        description=(
            "Devuelve vacunas vencidas, vacunas próximas (30 días) y "
            "tratamientos activos. Resultado cacheado 1 minuto."
        ),
        tags=["Alertas"],
    ),
)
class AlertaClinicaViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def list(self, request):
        try:
            clinica = request.user.perfil.clinica
        except (AttributeError, PerfilUsuario.DoesNotExist):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Tu cuenta no está asociada a ninguna clínica.")

        cache_key = f"alertas:clinica:{clinica.id}"

        # Intentar servir desde caché
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("Alertas servidas desde caché")
            return Response(cached)

        alertas: AlertasClinicaResult = obtener_alertas_clinicas(clinica=clinica, dias_anticipacion=30)

        # Serializar primero para evaluar los querysets una sola vez,
        # luego usar len() en lugar de .count() (evita 3 queries extra de COUNT)
        vencidas_data = VacunaSerializer(alertas.vacunas_vencidas, many=True).data
        proximas_data = VacunaSerializer(alertas.vacunas_proximas, many=True).data
        activos_data  = TratamientoSerializer(alertas.tratamientos_activos, many=True).data

        payload = {
            "fecha_revision": alertas.fecha_revision,
            "limite_revision": alertas.limite_revision,
            "resumen": {
                "vacunas_vencidas": len(vencidas_data),
                "vacunas_proximas": len(proximas_data),
                "tratamientos_activos": len(activos_data),
            },
            "vacunas_vencidas": vencidas_data,
            "vacunas_proximas": proximas_data,
            "tratamientos_activos": activos_data,
        }

        cache.set(cache_key, payload, timeout=settings.CACHE_TIMEOUT_ALERTAS)
        return Response(payload)
