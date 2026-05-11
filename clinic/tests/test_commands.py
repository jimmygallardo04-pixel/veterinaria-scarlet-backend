"""
Tests para los comandos de management de clinic.
"""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from clinic.models import CodigoVerificacion


class LimpiarCodigosExpiradosTest(TestCase):
    """Tests para el comando limpiar_codigos_expirados."""

    def _crear_codigo(self, email: str, dias_atras: int, usado: bool = False) -> CodigoVerificacion:
        """Crea un CodigoVerificacion con expira_en en el pasado (hace dias_atras días)."""
        return CodigoVerificacion.objects.create(
            email=email,
            codigo="123456",
            expira_en=timezone.now() - timedelta(days=dias_atras),
            usado=usado,
        )

    def test_elimina_codigos_expirados(self):
        """Elimina registros cuya expira_en es anterior al límite."""
        # Código expirado hace 2 días
        self._crear_codigo("viejo@test.cl", dias_atras=2)
        self.assertEqual(CodigoVerificacion.objects.count(), 1)

        out = StringIO()
        call_command("limpiar_codigos_expirados", "--dias=1", stdout=out)

        self.assertEqual(CodigoVerificacion.objects.count(), 0)
        self.assertIn("Eliminados 1", out.getvalue())

    def test_no_elimina_codigos_recientes(self):
        """No elimina registros cuya expira_en es posterior al límite."""
        # Código que expira en el futuro (creado ahora, expira en 15 min)
        CodigoVerificacion.objects.create(
            email="reciente@test.cl",
            codigo="654321",
            expira_en=timezone.now() + timedelta(minutes=15),
        )
        self.assertEqual(CodigoVerificacion.objects.count(), 1)

        out = StringIO()
        call_command("limpiar_codigos_expirados", "--dias=1", stdout=out)

        # El código reciente no debe eliminarse
        self.assertEqual(CodigoVerificacion.objects.count(), 1)
        self.assertIn("Eliminados 0", out.getvalue())

    def test_dry_run_no_elimina(self):
        """Con --dry-run muestra el conteo pero no elimina nada."""
        self._crear_codigo("dryrun@test.cl", dias_atras=2)
        self.assertEqual(CodigoVerificacion.objects.count(), 1)

        out = StringIO()
        call_command("limpiar_codigos_expirados", "--dias=1", "--dry-run", stdout=out)

        # No debe haber eliminado nada
        self.assertEqual(CodigoVerificacion.objects.count(), 1)
        self.assertIn("dry-run", out.getvalue())
        self.assertIn("1", out.getvalue())

    def test_respeta_parametro_dias(self):
        """El parámetro --dias controla el umbral de antigüedad."""
        # Código expirado hace 3 días
        self._crear_codigo("tres_dias@test.cl", dias_atras=3)
        # Código expirado hace 1 día
        self._crear_codigo("un_dia@test.cl", dias_atras=1)
        self.assertEqual(CodigoVerificacion.objects.count(), 2)

        out = StringIO()
        # Con --dias=2 solo elimina el de 3 días
        call_command("limpiar_codigos_expirados", "--dias=2", stdout=out)

        self.assertEqual(CodigoVerificacion.objects.count(), 1)
        self.assertIn("Eliminados 1", out.getvalue())
        self.assertTrue(
            CodigoVerificacion.objects.filter(email="un_dia@test.cl").exists()
        )

    def test_elimina_multiples_registros(self):
        """Elimina correctamente múltiples registros expirados."""
        for i in range(5):
            self._crear_codigo(f"multi{i}@test.cl", dias_atras=2)
        self.assertEqual(CodigoVerificacion.objects.count(), 5)

        out = StringIO()
        call_command("limpiar_codigos_expirados", "--dias=1", stdout=out)

        self.assertEqual(CodigoVerificacion.objects.count(), 0)
        self.assertIn("Eliminados 5", out.getvalue())

    def test_dias_cero_lanza_error(self):
        """--dias=0 lanza CommandError."""
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("limpiar_codigos_expirados", "--dias=0")

    def test_dias_negativo_lanza_error(self):
        """--dias negativo lanza CommandError."""
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("limpiar_codigos_expirados", "--dias=-1")
