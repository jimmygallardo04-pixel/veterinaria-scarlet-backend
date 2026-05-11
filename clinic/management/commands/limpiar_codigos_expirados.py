"""
Comando de management para limpiar registros de CodigoVerificacion expirados.

Uso:
    python manage.py limpiar_codigos_expirados
    python manage.py limpiar_codigos_expirados --dias 2
    python manage.py limpiar_codigos_expirados --dry-run

Recomendación: ejecutar diariamente via cron o tarea programada en Render.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from clinic.models import CodigoVerificacion

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Elimina registros de CodigoVerificacion expirados hace más de N días."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias",
            type=int,
            default=1,
            help="Eliminar registros con más de N días de antigüedad (default: 1, mínimo: 1).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostrar cuántos registros se eliminarían sin eliminarlos.",
        )

    def handle(self, *args, **options):
        dias = options["dias"]
        dry_run = options["dry_run"]

        if dias < 1:
            raise CommandError("--dias debe ser al menos 1.")

        limite = timezone.now() - timedelta(days=dias)

        qs = CodigoVerificacion.objects.filter(expira_en__lt=limite)

        if dry_run:
            count = qs.count()
            msg = (
                f"[dry-run] Se eliminarían {count} registro(s) de CodigoVerificacion "
                f"con más de {dias} día(s) de antigüedad."
            )
            self.stdout.write(self.style.WARNING(msg))
            logger.info(msg)
            return

        deleted, _ = qs.delete()
        msg = (
            f"Eliminados {deleted} registro(s) de CodigoVerificacion "
            f"con más de {dias} día(s) de antigüedad."
        )
        self.stdout.write(self.style.SUCCESS(msg))
        logger.info(msg)
