# Changelog — Veterinaria Scarlet Backend

## [Unreleased] - 2026-05-11

### Mejoras de seguridad y configuración

- **USE_TZ=True**: Activado el soporte de zonas horarias. Todos los datetimes se almacenan en UTC.
- **REGISTRO_SECRET_KEY**: Advertencia en logs al arrancar si la clave no está configurada.
- **REFRESH_TOKEN_LIFETIME**: Explícitamente configurado en 7 días (antes usaba el default implícito).
- **IntegrityError handling**: El handler de excepciones ahora captura `IntegrityError` y devuelve HTTP 409 con mensaje descriptivo.

### Mejoras de producción

- **Dockerfile**:
  - Agregado `HEALTHCHECK` que verifica `/api/schema/` cada 30s.
  - Workers de gunicorn configurables via `GUNICORN_WORKERS` (default: 3).
  - Cambiado de `psycopg2-binary` a `psycopg2` para mejor rendimiento.
- **requirements.txt**: `psycopg2` en lugar de `psycopg2-binary` (compilado contra librerías del sistema).

### Mejoras de desarrollo

- **pytest.ini**: `--durations=10` activado por defecto para detectar tests lentos.
- **test_settings.py**: `USE_TZ=True` explícito para consistencia con producción.
- **conftest.py**: Fixtures globales (`api_client`, `admin_user`, `vet_user`, `admin_client`, `vet_client`) para reducir duplicación en tests.
- **pagination.py**: `page_size` y `max_page_size` configurables via `API_PAGE_SIZE` y `API_MAX_PAGE_SIZE` en settings.

### Mejoras del admin de Django

- **Clinica y PerfilUsuario**: Ahora registrados en el admin para facilitar gestión de tenants.
- **Soft-delete support**: Todos los ModelAdmin ahora:
  - Muestran registros eliminados con filtro "Estado".
  - Tienen acción "Restaurar seleccionados".
  - Tienen acción "Soft-delete seleccionados".
  - Columna "Estado" (✅ Activo / 🗑 Eliminado) visible en la lista.

### Correcciones

- **sql/borrar-data.sql**: Agregadas tablas de catálogos (`clinic_especie`, `clinic_sexopaciente`, `clinic_tipoarchivodocumento`) que faltaban.
- **test_integration.py**: Tests de registro ahora usan `@override_settings(REGISTRO_SECRET_KEY="")` para no requerir la clave en tests.
- **serializers.py**: `_SoftDeleteNombreValidatorMixin` ahora detecta duplicados activos y eliminados por separado.
- **views.py**: 
  - Helper `_get_clinica_admin()` para evitar duplicación en vistas de veterinarios.
  - `sincronizar_email_admin_clinica()` sincroniza `User.email` cuando se edita `Clinica.email_admin`.
  - Import duplicado de `PermissionDenied` eliminado en `AlertaClinicaViewSet`.
- **serializers.py**: Eliminados `sorted()` redundantes en `FichaClinicaDetalleSerializer` (el ordering ya viene de la DB).
- **models.py**: Agregado índice en `CodigoVerificacion.expira_en` para optimizar queries de limpieza.
- **frontend/registro**: Cuando el email ya está registrado, el toast ofrece botón "Ir al login" en lugar de solo mostrar error.

### Migraciones

- `0017_add_index_codigo_expira_en.py`: Índice en `CodigoVerificacion.expira_en`.

---

## Notas de actualización

### Para desarrolladores

1. Ejecutar migraciones: `python manage.py migrate`
2. Si usas `psycopg2-binary` en local, puedes seguir usándolo (está en `.gitignore`). En producción se usa `psycopg2`.
3. Las fixtures globales de `conftest.py` están disponibles automáticamente en todos los tests.

### Para producción

1. Configurar `GUNICORN_WORKERS` según CPUs disponibles (regla: `2*CPU+1`).
2. Verificar que `REGISTRO_SECRET_KEY` esté configurada (el servidor loguea warning si falta).
3. El `HEALTHCHECK` del Dockerfile requiere que el contenedor responda en `/api/schema/` — verificar que el endpoint esté accesible.
4. `USE_TZ=True` requiere que la DB soporte datetimes aware (PostgreSQL lo soporta nativamente).
