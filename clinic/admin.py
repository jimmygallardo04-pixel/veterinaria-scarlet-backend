from django.contrib import admin
from .models import (
    Tutor,
    Paciente,
    FichaClinica,
    Cita,
    Vacuna,
    Tratamiento,
    ArchivoDocumento,
    Especie,
    SexoPaciente,
    TipoArchivoDocumento,
)

admin.site.register(Tutor)
admin.site.register(Paciente)
admin.site.register(FichaClinica)
admin.site.register(Cita)
admin.site.register(Vacuna)
admin.site.register(Tratamiento)
admin.site.register(ArchivoDocumento)
admin.site.register(Especie)
admin.site.register(SexoPaciente)
admin.site.register(TipoArchivoDocumento)