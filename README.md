# Veterinaria Scarlet — Backend

API REST construida con Django 5 + Django REST Framework. Gestión clínica veterinaria: pacientes, fichas, citas, vacunas, tratamientos y documentos.

## Stack

- Python 3.11 / Django 5.2
- Django REST Framework 3.17
- Simple JWT (autenticación)
- PostgreSQL (Supabase)
- drf-spectacular (documentación OpenAPI)
- Gunicorn + WhiteNoise (producción)
- Render (deployment)

## Levantar en local

```bash
# 1. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env  # editar con tus valores reales

# 4. Migrar base de datos
python manage.py migrate

# 5. Crear superusuario
python manage.py createsuperuser

# 6. Levantar servidor
python manage.py runserver
```

## Variables de entorno

Ver `.env.example` para la lista completa con descripciones. Las obligatorias son:

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SECRET_KEY` | Clave secreta Django | `django-insecure-...` |
| `DEBUG` | Modo debug | `True` (local) / `False` (prod) |
| `DATABASE_URL` | URL de PostgreSQL | `postgresql://user:pass@host/db` |
| `ALLOWED_HOSTS` | Hosts permitidos | `localhost,mi-backend.onrender.com` |
| `CORS_ALLOWED_ORIGINS` | Orígenes CORS | `http://localhost:3000` |

## Roles de usuario

El sistema tiene dos roles:

- **admin** — acceso completo, puede modificar catálogos
- **veterinario** — acceso clínico de lectura/escritura, sin acceso a configuración

Para asignar rol admin: desde el Django Admin (`/admin/`), crear el grupo `admin` y agregar el usuario a ese grupo. Los usuarios sin ese grupo son veterinarios por defecto.

## Endpoints

Todos los endpoints requieren `Authorization: Bearer <access_token>` salvo los de auth.

### Autenticación

```
POST   /api/v1/registro/    → registrar nueva clínica (devuelve tokens JWT)
POST   /api/v1/login/       → obtener tokens JWT
POST   /api/v1/refresh/     → renovar access token
GET    /api/v1/me/          → usuario autenticado + rol
```

### Recursos clínicos

```
GET/POST/PUT/DELETE   /api/v1/pacientes/
GET/POST/PUT/DELETE   /api/v1/tutores/
GET/POST/PUT/DELETE   /api/v1/fichas/
GET/POST/PUT/DELETE   /api/v1/citas/
GET/POST/PUT/DELETE   /api/v1/vacunas/
GET/POST/PUT/DELETE   /api/v1/tratamientos/
GET/POST/PUT/DELETE   /api/v1/archivos/
GET                   /api/v1/alertas/
```

### Catálogos (solo admin puede modificar)

```
GET/POST/PUT/DELETE   /api/v1/especies/
GET/POST/PUT/DELETE   /api/v1/sexos/
GET/POST/PUT/DELETE   /api/v1/tipos-archivo/
```

### Documentación interactiva

```
GET   /api/docs/     → Swagger UI
GET   /api/redoc/    → ReDoc
GET   /api/schema/   → Esquema OpenAPI (JSON/YAML)
```

### Parámetros de búsqueda y paginación

```
GET /api/v1/pacientes/?search=firulais     → búsqueda por nombre, tutor o especie
GET /api/v1/citas/?paciente=42             → filtrar por paciente
GET /api/v1/pacientes/?page=2&page_size=10 → paginación (máx. 100 por página)
```

## Mantenimiento

### Limpiar códigos OTP expirados

Los registros de `CodigoVerificacion` se acumulan en la DB. Ejecutar periódicamente:

```bash
# Ver cuántos se eliminarían (sin borrar)
python manage.py limpiar_codigos_expirados --dry-run

# Eliminar registros con más de 1 día de antigüedad (default)
python manage.py limpiar_codigos_expirados

# Eliminar registros con más de 7 días
python manage.py limpiar_codigos_expirados --dias 7
```

**En Render:** Render Free Tier no tiene cron jobs nativos. Opciones:

1. **Render Cron Job** (plan pago): crear un servicio de tipo "Cron Job" con el comando:
   ```
   python manage.py limpiar_codigos_expirados
   ```
   y schedule `0 3 * * *` (3 AM diario).

2. **GitHub Actions** (gratuito): crear un workflow que haga `curl` al endpoint de Render o ejecute el comando via SSH.

3. **cron-job.org** (gratuito): servicio externo que llama a un endpoint protegido de tu API que ejecuta la limpieza.

## Correr tests```bash
# Todos los tests
pytest

# Con reporte de cobertura
pytest --cov=clinic --cov-report=term-missing

# Solo tests unitarios (rápidos, sin Hypothesis)
pytest clinic/tests/test_models.py clinic/tests/test_services.py clinic/tests/test_serializers.py -v

# Un test específico
pytest clinic/tests/test_services.py::RegistrarClinicaTest -v
```

Los tests usan SQLite en memoria (configurado en `config/test_settings.py`), no requieren conexión a PostgreSQL.

## Deployment en Render

1. Conectar repositorio en Render
2. **Build command:**
   ```
   pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput --skip-checks
   ```
3. **Start command:**
   ```
   gunicorn config.wsgi:application
   ```
4. Configurar variables de entorno en el panel de Render:
   - `DEBUG=False`
   - `SECRET_KEY=<clave segura>`
   - `DATABASE_URL=<url de supabase>`
   - `ALLOWED_HOSTS=mi-backend.onrender.com`
   - `CORS_ALLOWED_ORIGINS=https://mi-frontend.vercel.app`

## Configurar dominio propio en Render

1. **Añadir el dominio** en tu servicio → Settings → Custom Domains → Add Custom Domain
2. Añadir el registro CNAME en tu proveedor de DNS (Render lo indica)
3. **Actualizar variables de entorno:**
   ```
   ALLOWED_HOSTS=api.mivetapp.cl,mi-backend.onrender.com
   CORS_ALLOWED_ORIGINS=https://mivetapp.cl,https://www.mivetapp.cl
   CSRF_TRUSTED_ORIGINS=https://mivetapp.cl,https://www.mivetapp.cl
   ```
4. Render redespliega automáticamente al guardar las variables

## Docker

```bash
# Build
docker build -t veterinaria-scarlet-backend .

# Run (requiere variables de entorno)
docker run -p 8000:8000 \
  -e SECRET_KEY=tu_clave \
  -e DATABASE_URL=tu_url \
  -e DEBUG=False \
  -e ALLOWED_HOSTS=localhost \
  veterinaria-scarlet-backend
```
