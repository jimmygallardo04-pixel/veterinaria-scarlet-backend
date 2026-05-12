"""
Handler global de excepciones para Django REST Framework.

Centraliza el formato de todos los errores de la API, asegurando respuestas
consistentes y logueo estructurado de errores inesperados.

Formato de respuesta de error:
    {
        "error": {
            "code": "CODIGO_ERROR",
            "message": "Descripción legible",
            "detail": { ... }   # opcional, solo en errores de validación
        }
    }
"""

import logging

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.http import Http404

from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied as DRFPermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

logger = logging.getLogger(__name__)

# Mapa de tipo de excepción → (código de error, mensaje por defecto)
_ERROR_MAP: dict[type, tuple[str, str]] = {
    NotAuthenticated: ("NOT_AUTHENTICATED", "Autenticación requerida."),
    AuthenticationFailed: ("AUTHENTICATION_FAILED", "Credenciales inválidas."),
    DRFPermissionDenied: ("PERMISSION_DENIED", "No tienes permiso para realizar esta acción."),
    PermissionDenied: ("PERMISSION_DENIED", "No tienes permiso para realizar esta acción."),
    NotFound: ("NOT_FOUND", "El recurso solicitado no existe."),
    Http404: ("NOT_FOUND", "El recurso solicitado no existe."),
    MethodNotAllowed: ("METHOD_NOT_ALLOWED", "Método HTTP no permitido."),
    Throttled: ("THROTTLED", "Demasiadas solicitudes. Intenta más tarde."),
    ValidationError: ("VALIDATION_ERROR", "Los datos enviados no son válidos."),
    ParseError: ("PARSE_ERROR", "El cuerpo de la solicitud no tiene un formato válido."),
}


def custom_exception_handler(exc: Exception, context: dict) -> Response | None:
    """
    Handler de excepciones personalizado para DRF.

    - Errores conocidos (4xx): respuesta estructurada sin stack trace.
    - Errores inesperados (5xx): logueo completo + respuesta genérica.
    - Errores de validación: incluye el detalle de campos en `detail`.
    """
    # Dejar que DRF procese primero para obtener el Response base
    response = drf_default_handler(exc, context)

    # Errores no manejados por DRF (Django nativo Http404, PermissionDenied, IntegrityError)
    if response is None:
        if isinstance(exc, Http404):
            response = Response(status=status.HTTP_404_NOT_FOUND)
        elif isinstance(exc, PermissionDenied):
            response = Response(status=status.HTTP_403_FORBIDDEN)
        elif isinstance(exc, IntegrityError):
            # Constraint de DB violada — loguearlo con detalle para diagnóstico
            view = context.get("view")
            request = context.get("request")
            logger.error(
                "IntegrityError en %s %s — vista: %s — detalle: %s",
                getattr(request, "method", "?"),
                getattr(request, "path", "?"),
                view.__class__.__name__ if view else "?",
                str(exc),
                exc_info=exc,
            )
            return Response(
                {
                    "error": {
                        "code": "CONFLICT",
                        "message": "El recurso ya existe o viola una restricción de unicidad.",
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )
        else:
            # Error inesperado — loguearlo con contexto completo
            view = context.get("view")
            request = context.get("request")
            logger.error(
                "Error inesperado en %s %s — vista: %s",
                getattr(request, "method", "?"),
                getattr(request, "path", "?"),
                view.__class__.__name__ if view else "?",
                exc_info=exc,
            )
            return Response(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Error interno del servidor. Por favor intenta nuevamente.",
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # Construir respuesta estructurada
    code, default_message = _ERROR_MAP.get(type(exc), ("ERROR", str(exc)))

    body: dict = {
        "error": {
            "code": code,
            "message": default_message,
        }
    }

    # Para errores de validación, incluir el detalle de campos
    if isinstance(exc, ValidationError):
        body["error"]["detail"] = response.data

    response.data = body
    return response
