"""
Managers personalizados para los modelos de la clínica.

ActiveManager filtra automáticamente los registros con soft-delete,
eliminando la necesidad de añadir `eliminado_en__isnull=True` en cada
get_queryset() de los ViewSets.
"""

from django.db import models


class ActiveManager(models.Manager):
    """
    Manager por defecto que excluye registros con soft-delete.

    Uso:
        class MiModelo(BaseModel):
            objects = ActiveManager()

    Cualquier queryset iniciado con MiModelo.objects ya filtra
    los registros eliminados. Para acceder a todos los registros
    (incluyendo eliminados), usar MiModelo.all_objects.all().
    """

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(eliminado_en__isnull=True)


class AllObjectsManager(models.Manager):
    """
    Manager sin filtros — devuelve todos los registros incluyendo
    los marcados como eliminados. Útil para auditoría y administración.
    """

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset()
