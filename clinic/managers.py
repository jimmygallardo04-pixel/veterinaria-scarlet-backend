"""
Managers personalizados para los modelos de la clínica.

ActiveManager filtra automáticamente los registros con soft-delete y
los que tienen activo=True, eliminando la necesidad de añadir filtros
manuales en cada get_queryset() de los ViewSets.
"""

from django.db import models


class ActiveManager(models.Manager):
    """
    Manager por defecto que excluye registros con soft-delete y los inactivos.

    Este manager filtra por:
    1. `eliminado_en__isnull=True` - excluye registros con soft-delete
    2. `activo=True` - si el modelo tiene el campo `activo`

    Uso:
        class MiModelo(BaseModel):
            objects = ActiveManager()

    Cualquier queryset iniciado con MiModelo.objects ya filtra
    los registros eliminados e inactivos. Para acceder a todos los registros
    (incluyendo eliminados e inactivos), usar MiModelo.all_objects.all().
    """

    def get_queryset(self) -> models.QuerySet:
        qs = super().get_queryset().filter(eliminado_en__isnull=True)
        # Si el modelo tiene campo 'activo', filtrar solo los activos
        # Usamos hasattr en el modelo (no en el queryset) para verificar
        if hasattr(self.model, 'activo'):
            qs = qs.filter(activo=True)
        return qs


class AllObjectsManager(models.Manager):
    """
    Manager sin filtros — devuelve todos los registros incluyendo
    los marcados como eliminados. Útil para auditoría y administración.
    """

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset()
