"""
Configuración del admin de Django para Veterinaria Scarlet.

Cada ModelAdmin define los campos visibles en la lista, los filtros
laterales y los campos de búsqueda para facilitar la gestión de datos
desde el panel de administración.

Soft-delete:
    Los modelos que heredan de BaseModel tienen un campo `eliminado_en`.
    Por defecto el ActiveManager los oculta. Cada ModelAdmin que soporte
    soft-delete incluye:
      - Un filtro "Mostrar eliminados" para verlos.
      - Una acción "Restaurar seleccionados" para reactivarlos.
      - `get_queryset` que usa `all_objects` para que el admin pueda verlos.
"""

from django.contrib import admin
from django.utils import timezone

from .models import (
    ArchivoDocumento,
    Cita,
    Clinica,
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


# ─── Mixin: soporte de soft-delete en el admin ────────────────────────────────

class SoftDeleteAdminMixin:
    """
    Mixin para ModelAdmin que añade:
      - Visibilidad de registros soft-deleted (usa all_objects).
      - Filtro lateral "Estado" (activo / eliminado).
      - Acción "Restaurar seleccionados".
      - Acción "Eliminar (soft-delete) seleccionados".
    """

    def get_queryset(self, request):
        # Usar all_objects para que el admin vea también los eliminados
        return self.model.all_objects.all()

    @admin.action(description="Restaurar seleccionados (deshacer eliminación)")
    def restaurar_seleccionados(self, request, queryset):
        count = queryset.update(eliminado_en=None)
        self.message_user(request, f"{count} registro(s) restaurado(s).")

    @admin.action(description="Soft-delete seleccionados")
    def soft_delete_seleccionados(self, request, queryset):
        count = queryset.filter(eliminado_en__isnull=True).update(
            eliminado_en=timezone.now()
        )
        self.message_user(request, f"{count} registro(s) marcado(s) como eliminado(s).")

    actions = ["restaurar_seleccionados", "soft_delete_seleccionados"]

    def estado_soft_delete(self, obj):
        return "✅ Activo" if obj.eliminado_en is None else "🗑 Eliminado"
    estado_soft_delete.short_description = "Estado"


# ─── Multi-tenancy ────────────────────────────────────────────────────────────

@admin.register(Clinica)
class ClinicaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "email_admin", "creado_en")
    search_fields = ("nombre", "email_admin")
    ordering = ("nombre",)
    readonly_fields = ("creado_en",)


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ("user", "clinica", "rol")
    list_filter = ("rol", "clinica")
    search_fields = ("user__email", "user__first_name", "clinica__nombre")
    ordering = ("clinica__nombre", "user__email")
    autocomplete_fields = ("clinica",)
    raw_id_fields = ("user",)


# ─── Catálogos ────────────────────────────────────────────────────────────────

@admin.register(Especie)
class EspecieAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "clinica", "estado_soft_delete", "creado_en")
    list_filter = ("clinica",)
    search_fields = ("nombre",)
    ordering = ("nombre",)
    readonly_fields = ("creado_en", "actualizado_en")


@admin.register(SexoPaciente)
class SexoPacienteAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "clinica", "estado_soft_delete", "creado_en")
    list_filter = ("clinica",)
    search_fields = ("nombre",)
    ordering = ("nombre",)
    readonly_fields = ("creado_en", "actualizado_en")


@admin.register(TipoArchivoDocumento)
class TipoArchivoDocumentoAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "clinica", "estado_soft_delete", "creado_en")
    list_filter = ("clinica",)
    search_fields = ("nombre",)
    ordering = ("nombre",)
    readonly_fields = ("creado_en", "actualizado_en")


# ─── Entidades principales ────────────────────────────────────────────────────

@admin.register(Tutor)
class TutorAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "clinica", "telefono", "email", "rut", "estado_soft_delete", "creado_en")
    list_filter = ("clinica",)
    search_fields = ("nombre", "rut", "email", "telefono")
    ordering = ("nombre",)
    readonly_fields = ("creado_en", "actualizado_en")


@admin.register(Paciente)
class PacienteAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "clinica", "especie", "tutor", "sexo", "esterilizado", "estado_soft_delete", "creado_en")
    list_filter = ("clinica", "especie", "sexo", "esterilizado")
    search_fields = ("nombre", "tutor__nombre", "raza", "color")
    ordering = ("-creado_en",)
    readonly_fields = ("creado_en", "actualizado_en", "edad")
    autocomplete_fields = ("tutor", "especie", "sexo")


@admin.register(FichaClinica)
class FichaClinicaAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("paciente", "clinica", "fecha", "motivo_consulta", "diagnostico", "estado_soft_delete", "creado_en")
    list_filter = ("clinica", "fecha")
    search_fields = ("paciente__nombre", "motivo_consulta", "diagnostico")
    ordering = ("-fecha",)
    readonly_fields = ("creado_en", "actualizado_en")
    autocomplete_fields = ("paciente",)
    date_hierarchy = "fecha"


@admin.register(Cita)
class CitaAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("paciente", "clinica", "tutor", "fecha_hora", "estado", "motivo", "estado_soft_delete")
    list_filter = ("clinica", "estado", "fecha_hora")
    search_fields = ("paciente__nombre", "tutor__nombre", "motivo")
    ordering = ("-fecha_hora",)
    readonly_fields = ("creado_en", "actualizado_en")
    autocomplete_fields = ("paciente", "tutor")
    date_hierarchy = "fecha_hora"


@admin.register(Vacuna)
class VacunaAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("nombre_vacuna", "clinica", "paciente", "fecha_aplicacion", "proxima_dosis", "estado_soft_delete")
    list_filter = ("clinica", "fecha_aplicacion", "proxima_dosis")
    search_fields = ("nombre_vacuna", "paciente__nombre")
    ordering = ("-fecha_aplicacion",)
    readonly_fields = ("creado_en", "actualizado_en")
    autocomplete_fields = ("paciente",)


@admin.register(Tratamiento)
class TratamientoAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("medicamento", "clinica", "paciente", "dosis", "frecuencia", "fecha_inicio", "fecha_fin", "estado_soft_delete")
    list_filter = ("clinica", "fecha_inicio", "fecha_fin")
    search_fields = ("medicamento", "paciente__nombre")
    ordering = ("-fecha_inicio",)
    readonly_fields = ("creado_en", "actualizado_en")
    autocomplete_fields = ("paciente",)


@admin.register(ArchivoDocumento)
class ArchivoDocumentoAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("paciente", "clinica", "tipo", "fecha", "archivo_url", "estado_soft_delete")
    list_filter = ("clinica", "tipo", "fecha")
    search_fields = ("paciente__nombre", "tipo__nombre")
    ordering = ("-fecha",)
    readonly_fields = ("creado_en", "actualizado_en")
    autocomplete_fields = ("paciente", "tipo")
