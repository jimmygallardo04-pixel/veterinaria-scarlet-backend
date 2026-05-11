"""
Data migration: asignar clínica a registros existentes y crear perfiles de usuario.

Este script:
1. Crea (o recupera) una Clinica de migración para datos huérfanos.
2. Asigna esa clínica a todos los registros de dominio que no tienen clinica_id.
3. Crea un PerfilUsuario para cada User que no tenga uno, asignando rol según
   si el usuario es superusuario o pertenece al grupo "admin".

Debe ejecutarse DESPUÉS de 0010_archivodocumento_clinica_cita_clinica_and_more
y ANTES de la migración que hace clinica NOT NULL.
"""

from django.db import migrations


MODELOS_DOMINIO = [
    "Tutor",
    "Paciente",
    "FichaClinica",
    "Cita",
    "Vacuna",
    "Tratamiento",
    "ArchivoDocumento",
    "Especie",
    "SexoPaciente",
    "TipoArchivoDocumento",
]

EMAIL_CLINICA_MIGRADA = "migrada@veterinariascarlet.cl"
NOMBRE_CLINICA_MIGRADA = "Clínica Migrada"


def migrar_datos(apps, schema_editor):
    """
    Asigna la clínica migrada a todos los registros huérfanos y crea
    PerfilUsuario para cada User que no tenga uno.
    """
    Clinica = apps.get_model("clinic", "Clinica")
    PerfilUsuario = apps.get_model("clinic", "PerfilUsuario")
    User = apps.get_model("auth", "User")

    # 1. Crear (o recuperar) la clínica de migración
    clinica_migrada, _ = Clinica.objects.get_or_create(
        email_admin=EMAIL_CLINICA_MIGRADA,
        defaults={"nombre": NOMBRE_CLINICA_MIGRADA, "activo": True},
    )

    # 2. Asignar la clínica a todos los registros de dominio sin clinica_id
    for model_name in MODELOS_DOMINIO:
        Model = apps.get_model("clinic", model_name)
        Model.objects.filter(clinica__isnull=True).update(clinica=clinica_migrada)

    # 3. Crear PerfilUsuario para cada User sin perfil
    # Obtener IDs de usuarios que pertenecen al grupo "admin"
    admin_user_ids = set(
        User.objects.filter(groups__name="admin").values_list("id", flat=True)
    )

    # Usuarios que ya tienen PerfilUsuario
    usuarios_con_perfil = set(
        PerfilUsuario.objects.values_list("user_id", flat=True)
    )

    for user in User.objects.all():
        if user.pk in usuarios_con_perfil:
            continue
        rol = "admin" if (user.is_superuser or user.pk in admin_user_ids) else "veterinario"
        PerfilUsuario.objects.create(
            user=user,
            clinica=clinica_migrada,
            rol=rol,
        )


def revertir_datos(apps, schema_editor):
    """
    Revierte la data migration:
    - Elimina la clínica migrada (CASCADE elimina los PerfilUsuario asociados
      y desvincula los registros de dominio).
    - Elimina los PerfilUsuario que apuntan a la clínica migrada (por si CASCADE
      no los eliminó antes de que se borre la clínica).

    Nota: los registros de dominio quedarán con clinica_id=NULL tras el rollback,
    lo cual es válido porque la migración de esquema los definió como nullable.
    """
    Clinica = apps.get_model("clinic", "Clinica")

    # Eliminar la clínica migrada; CASCADE se encarga de los PerfilUsuario
    # y de poner clinica_id=NULL en los registros de dominio (si on_delete=SET_NULL)
    # o de eliminarlos (si on_delete=CASCADE). En este caso es CASCADE, pero como
    # los campos son nullable en este punto de la historia de migraciones, Django
    # no eliminará los registros de dominio — solo los PerfilUsuario.
    Clinica.objects.filter(email_admin=EMAIL_CLINICA_MIGRADA).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0010_archivodocumento_clinica_cita_clinica_and_more"),
    ]

    operations = [
        migrations.RunPython(migrar_datos, revertir_datos),
    ]
