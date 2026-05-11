FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python antes de copiar el código
# (aprovecha la caché de capas de Docker si requirements.txt no cambia)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY . .

# Recolectar archivos estáticos en build time.
# --skip-checks evita que Django intente conectarse a la DB durante el build.
RUN mkdir -p /app/staticfiles && \
    DEBUG=False \
    SECRET_KEY=dummy-build-key-not-used-in-production \
    ALLOWED_HOSTS=localhost \
    DATABASE_URL=sqlite:///tmp/build.db \
    python manage.py collectstatic --noinput --skip-checks

# Crear usuario no-root para ejecutar la aplicación.
# Nunca correr contenedores de producción como root.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
