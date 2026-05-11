"""
Configuración del admin de Django para Veterinaria Scarlet.

Cada ModelAdmin define los campos visibles en la lista, los filtros
laterales y los campos de búsqueda para facilitar la gestión de datos
desde el panel de administración.
"""

from django.contrib import admin

from .models import (
    ArchivoDocumento,
    Cita,
    Especie,
    FichaClinica,
    Paciente,
    SexoPaciente,
    TipoArchivoDocumento,
    Tratamiento,
    Tutor,
    Vacuna,
)


# ─── Catálogos ────────────────────────────────────────────────────────────────

@admin.register(Especie)
class EspecieAdmin(admin.ModelAdmin):
    list_display = ("nombre", "creado_en")
    search_fields = ("nombre",)
    ordering = ("nombre",)
    readonly_fields = ("creado_en", "actualizado_en")


@admin.register(SexoPaciente)
class SexoPacienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "creado_en")
    search_fields = ("nombre",)
    ordering = ("nombre",)
    readonly_fields = ("creado_en", "actualizado_en")


@admin.register(TipoArchivoDocumento)
class TipoArchivoDocumentoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "creado_en")
    search_fields = ("nombre",)
    ordering = ("nombre",)
    readonly_fields = ("creado_en", "actualizado_en")


# ─── Entidades principales ────────────────────────────────────────────────────

@admin.register(Tutor)
class TutorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "telefono", "email", "rut", "creado_en")
    search_fields = ("nombre", "rut", "email", "telefono")
    ordering = ("nombre",)
    readonly_fields = ("creado_en", "actualizado_en")


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "especie", "tutor", "sexo", "esterilizado", "creado_en")
    list_filter = ("especie", "sexo", "esterilizado")
    search_fields = ("nombre", "tutor__nombre", "raza", "color")
    ordering = ("-creado_en",)
    readonly_fields = ("creado_en", "actualizado_en", "edad")
    autocomplete_fields = ("tutor", "especie", "sexo")


@admin.register(FichaClinica)
class FichaClinicaAdmin(admin.ModelAdmin):
    list_display = ("paciente", "fecha", "motivo_consulta", "diagnostico", "creado_en")
    list_filter = ("fecha",)
    search_fields = ("paciente__nombre", "motivo_consulta", "diagnostico")
    ordering = ("-fecha",)
    readonly_fields = ("creado_en", "actualizado_en")
    autocomplete_fields = ("paciente",)
    date_hierarchy = "fecha"


@admin.register(Cita)
class CitaAdmin(admin.ModelAdmin):
    list_display = ("paciente", "tutor", "fecha_hora", "estado", "motivo")
    list_filter = ("estado", "fecha_hora")
    search_fields = ("paciente__nombre", "tutor__nombre", "motivo")
    ordering = ("-fecha_hora",)
    readonly_fields = ("creado_en", "actualizado_en")
    autocomplete_fields = ("paciente", "tutor")
    date_hierarchy = "fecha_hora"


@admin.register(Vacuna)
class VacunaAdmin(admin.ModelAdmin):
    list_display = ("nombre_vacuna", "paciente", "fecha_aplicacion", "proxima_dosis")
    list_filter = ("fecha_aplicacion", "proxima_dosis")
    search_fields = ("nombre_vacuna", "paciente__nombre")
    ordering = ("-fecha_aplicacion",)
    readonly_fields = ("creado_en", "actualizado_en")
    autocomplete_fields = ("paciente",)


@admin.register(Tratamiento)
class TratamientoAdmin(admin.ModelAdmin):
    list_display = ("medicamento", "paciente", "dosis", "frecuencia", "fecha_inicio", "fecha_fin")
    list_filter = ("fecha_inicio", "fecha_fin")
    search_fields = ("medicamento", "paciente__nombre")
    ordering = ("-fecha_inicio",)
    readonly_fields = ("creado_en", "actualizado_en")
    autocomplete_fields = ("paciente",)


@admin.register(ArchivoDocumento)
class ArchivoDocumentoAdmin(admin.ModelAdmin):
    list_display = ("paciente", "tipo", "fecha", "archivo_url")
    list_filter = ("tipo", "fecha")
    search_fields = ("paciente__nombre", "tipo__nombre")
    ordering = ("-fecha",)
    readonly_fields = ("creado_en", "actualizado_en")
    autocomplete_fields = ("paciente", "tipo")
