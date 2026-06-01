#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from clinic.models import Clinica, PerfilUsuario

# Crear clínica de prueba
clinica, created = Clinica.objects.get_or_create(
    nombre="Clínica Test",
    defaults={"email_admin": "test@test.com"}
)
print(f"Clínica: {clinica.nombre} (UUID: {clinica.uuid}), created={created}")


# Crear usuario
user, created = User.objects.get_or_create(
    username="testuser",
    defaults={
        "email": "testuser@test.com",
        "first_name": "Test",
        "last_name": "User"
    }
)
if created:
    user.set_password("testpass123")
    user.save()
    print(f"Usuario creado: {user.username}")
else:
    print(f"Usuario ya existe: {user.username}")

# Crear perfil
perfil, created = PerfilUsuario.objects.get_or_create(
    user=user,
    defaults={
        "clinica": clinica,
        "rol": PerfilUsuario.Rol.VETERINARIO
    }
)
print(f"Perfil creado: {perfil}, role={perfil.rol}")
print(f"\n✓ Credenciales: username=testuser, password=testpass123")
