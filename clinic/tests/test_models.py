"""
Tests unitarios de modelos.

Verifican la lógica de negocio encapsulada en los modelos sin hacer
ninguna llamada HTTP. Son rápidos y no dependen de DRF.
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from clinic.models import (
    BaseModel,
    Clinica,
    Especie,
    FichaClinica,
    Paciente,
    PerfilUsuario,
    SexoPaciente,
    Tratamiento,
    Tutor,
    Vacuna,
)
from .helpers import make_especie, make_paciente, make_sexo, make_tutor


# ─── BaseModel: soft-delete ───────────────────────────────────────────────────

class SoftDeleteTest(TestCase):
    """BaseModel.soft_delete() y is_active() funcionan correctamente."""

    def setUp(self):
        from clinic.models import Clinica
        clinica, _ = Clinica.objects.get_or_create(
            email_admin="softdelete@test.cl",
            defaults={"nombre": "Clínica SoftDelete", "activo": True},
        )
        self.especie = Especie.objects.create(nombre="Gato", clinica=clinica)

    def test_is_active_true_por_defecto(self):
        self.assertTrue(self.especie.is_active())
        self.assertIsNone(self.especie.eliminado_en)

    def test_soft_delete_marca_eliminado_en(self):
        self.especie.soft_delete()
        self.especie.refresh_from_db()
        self.assertIsNotNone(self.especie.eliminado_en)
        self.assertFalse(self.especie.is_active())

    def test_soft_delete_no_borra_de_la_db(self):
        pk = self.especie.pk
        self.especie.soft_delete()
        # all_objects incluye eliminados
        self.assertTrue(Especie.all_objects.filter(pk=pk).exists())

    def test_active_manager_excluye_eliminados(self):
        self.especie.soft_delete()
        # objects (ActiveManager) no debe devolver el registro eliminado
        self.assertFalse(Especie.objects.filter(pk=self.especie.pk).exists())

    def test_all_objects_incluye_eliminados(self):
        self.especie.soft_delete()
        self.assertTrue(Especie.all_objects.filter(pk=self.especie.pk).exists())

    def test_soft_delete_actualiza_actualizado_en(self):
        antes = self.especie.actualizado_en
        self.especie.soft_delete()
        self.especie.refresh_from_db()
        self.assertGreaterEqual(self.especie.actualizado_en, antes)


# ─── Paciente.edad ────────────────────────────────────────────────────────────

class PacienteEdadTest(TestCase):
    """Paciente.edad calcula correctamente la edad en años completos."""

    def setUp(self):
        self.tutor = make_tutor()

    def _paciente(self, fecha_nacimiento):
        return Paciente(
            tutor=self.tutor,
            nombre="Test",
            especie=make_especie(),
            sexo=make_sexo(),
            fecha_nacimiento=fecha_nacimiento,
        )

    def test_edad_none_sin_fecha_nacimiento(self):
        p = self._paciente(None)
        self.assertIsNone(p.edad)

    def test_edad_exacta_en_cumpleanos(self):
        hoy = date.today()
        nacimiento = hoy.replace(year=hoy.year - 3)
        p = self._paciente(nacimiento)
        self.assertEqual(p.edad, 3)

    def test_edad_antes_del_cumpleanos(self):
        hoy = date.today()
        # Nacido hace 5 años pero el cumpleaños aún no llegó este año
        nacimiento = date(hoy.year - 5, hoy.month, hoy.day) + timedelta(days=1)
        p = self._paciente(nacimiento)
        self.assertEqual(p.edad, 4)

    def test_edad_cero_recien_nacido(self):
        p = self._paciente(date.today())
        self.assertEqual(p.edad, 0)

    def test_edad_un_anio(self):
        p = self._paciente(date.today() - timedelta(days=365))
        # Puede ser 0 o 1 dependiendo del día exacto, pero nunca negativo
        self.assertGreaterEqual(p.edad, 0)


# ─── Vacuna.clean() ───────────────────────────────────────────────────────────

class VacunaCleanTest(TestCase):
    """Vacuna.clean() valida que proxima_dosis sea posterior a fecha_aplicacion."""

    def setUp(self):
        tutor = make_tutor()
        self.paciente = make_paciente(tutor)

    def _vacuna(self, fecha_aplicacion, proxima_dosis):
        return Vacuna(
            paciente=self.paciente,
            nombre_vacuna="Rabia",
            fecha_aplicacion=fecha_aplicacion,
            proxima_dosis=proxima_dosis,
        )

    def test_proxima_dosis_posterior_es_valida(self):
        hoy = date.today()
        v = self._vacuna(hoy, hoy + timedelta(days=30))
        # No debe lanzar excepción
        v.clean()

    def test_proxima_dosis_igual_lanza_error(self):
        hoy = date.today()
        v = self._vacuna(hoy, hoy)
        with self.assertRaises(ValidationError) as ctx:
            v.clean()
        self.assertIn("proxima_dosis", ctx.exception.message_dict)

    def test_proxima_dosis_anterior_lanza_error(self):
        hoy = date.today()
        v = self._vacuna(hoy, hoy - timedelta(days=1))
        with self.assertRaises(ValidationError) as ctx:
            v.clean()
        self.assertIn("proxima_dosis", ctx.exception.message_dict)

    def test_sin_proxima_dosis_no_valida(self):
        hoy = date.today()
        v = self._vacuna(hoy, None)
        # Sin proxima_dosis no hay nada que validar
        v.clean()


# ─── Tratamiento.clean() ─────────────────────────────────────────────────────

class TratamientoCleanTest(TestCase):
    """Tratamiento.clean() valida que fecha_fin >= fecha_inicio."""

    def setUp(self):
        tutor = make_tutor()
        self.paciente = make_paciente(tutor)

    def _tratamiento(self, fecha_inicio, fecha_fin):
        return Tratamiento(
            paciente=self.paciente,
            medicamento="Amoxicilina",
            dosis="250mg",
            frecuencia="Cada 8h",
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )

    def test_fecha_fin_posterior_es_valida(self):
        hoy = date.today()
        t = self._tratamiento(hoy, hoy + timedelta(days=7))
        t.clean()  # no debe lanzar

    def test_fecha_fin_igual_es_valida(self):
        hoy = date.today()
        t = self._tratamiento(hoy, hoy)
        t.clean()  # mismo día es válido

    def test_fecha_fin_anterior_lanza_error(self):
        hoy = date.today()
        t = self._tratamiento(hoy, hoy - timedelta(days=1))
        with self.assertRaises(ValidationError) as ctx:
            t.clean()
        self.assertIn("fecha_fin", ctx.exception.message_dict)

    def test_sin_fecha_fin_no_valida(self):
        hoy = date.today()
        t = self._tratamiento(hoy, None)
        t.clean()  # tratamiento indefinido es válido


# ─── Catálogos: sin campo activo ─────────────────────────────────────────────

class CatalogoSinActivoTest(TestCase):
    """Los catálogos usan solo soft-delete, sin campo activo redundante."""

    def test_especie_no_tiene_campo_activo(self):
        from clinic.models import Clinica
        clinica, _ = Clinica.objects.get_or_create(
            email_admin="catalogo@test.cl",
            defaults={"nombre": "Clínica Catálogo", "activo": True},
        )
        e = Especie.objects.create(nombre="Conejo", clinica=clinica)
        self.assertFalse(hasattr(e, "activo"))

    def test_sexo_no_tiene_campo_activo(self):
        from clinic.models import Clinica
        clinica, _ = Clinica.objects.get_or_create(
            email_admin="catalogo@test.cl",
            defaults={"nombre": "Clínica Catálogo", "activo": True},
        )
        s = SexoPaciente.objects.create(nombre="Hembra", clinica=clinica)
        self.assertFalse(hasattr(s, "activo"))

    def test_especie_eliminada_no_aparece_en_objects(self):
        from clinic.models import Clinica
        clinica, _ = Clinica.objects.get_or_create(
            email_admin="catalogo@test.cl",
            defaults={"nombre": "Clínica Catálogo", "activo": True},
        )
        e = Especie.objects.create(nombre="Hamster", clinica=clinica)
        e.soft_delete()
        self.assertNotIn(e, Especie.objects.all())

    def test_especie_str(self):
        e = Especie(nombre="Tortuga")
        self.assertEqual(str(e), "Tortuga")


# ─── Clinica ──────────────────────────────────────────────────────────────────

class ClinicaStrTest(TestCase):
    """Clinica.__str__ devuelve el nombre de la clínica.

    Valida: Requisito 1.1
    """

    def test_str_devuelve_nombre(self):
        clinica = Clinica(nombre="Veterinaria Scarlet", email_admin="admin@scarlet.cl")
        self.assertEqual(str(clinica), "Veterinaria Scarlet")

    def test_str_devuelve_nombre_guardado(self):
        clinica = Clinica.objects.create(
            nombre="Clínica Los Pinos",
            email_admin="admin@lospinos.cl",
        )
        self.assertEqual(str(clinica), "Clínica Los Pinos")


# ─── PerfilUsuario ────────────────────────────────────────────────────────────

class PerfilUsuarioStrTest(TestCase):
    """PerfilUsuario.__str__ incluye email, nombre de clínica y rol.

    Valida: Requisito 1.2
    """

    def setUp(self):
        self.clinica = Clinica.objects.create(
            nombre="Clínica Test",
            email_admin="admin@test.cl",
        )
        self.user = User.objects.create_user(
            username="vet@test.cl",
            email="vet@test.cl",
            password="testpass123",
        )

    def test_str_incluye_email(self):
        perfil = PerfilUsuario.objects.create(
            user=self.user,
            clinica=self.clinica,
            rol=PerfilUsuario.Rol.VETERINARIO,
        )
        self.assertIn(self.user.email, str(perfil))

    def test_str_incluye_nombre_clinica(self):
        perfil = PerfilUsuario.objects.create(
            user=self.user,
            clinica=self.clinica,
            rol=PerfilUsuario.Rol.VETERINARIO,
        )
        self.assertIn(self.clinica.nombre, str(perfil))

    def test_str_incluye_rol(self):
        perfil = PerfilUsuario.objects.create(
            user=self.user,
            clinica=self.clinica,
            rol=PerfilUsuario.Rol.ADMIN,
        )
        self.assertIn(PerfilUsuario.Rol.ADMIN, str(perfil))

    def test_str_formato_completo(self):
        perfil = PerfilUsuario.objects.create(
            user=self.user,
            clinica=self.clinica,
            rol=PerfilUsuario.Rol.VETERINARIO,
        )
        expected = f"{self.user.email} — {self.clinica.nombre} ({PerfilUsuario.Rol.VETERINARIO})"
        self.assertEqual(str(perfil), expected)


class PerfilUsuarioUnicoTest(TestCase):
    """Crear dos PerfilUsuario para el mismo User lanza IntegrityError.

    Valida: Requisitos 1.4, 1.5
    """

    def setUp(self):
        self.clinica = Clinica.objects.create(
            nombre="Clínica Única",
            email_admin="admin@unica.cl",
        )
        self.user = User.objects.create_user(
            username="usuario@unica.cl",
            email="usuario@unica.cl",
            password="testpass123",
        )

    def test_segundo_perfil_mismo_user_lanza_integrity_error(self):
        PerfilUsuario.objects.create(
            user=self.user,
            clinica=self.clinica,
            rol=PerfilUsuario.Rol.ADMIN,
        )
        clinica2 = Clinica.objects.create(
            nombre="Otra Clínica",
            email_admin="admin@otra.cl",
        )
        with self.assertRaises(IntegrityError):
            PerfilUsuario.objects.create(
                user=self.user,
                clinica=clinica2,
                rol=PerfilUsuario.Rol.VETERINARIO,
            )


class PerfilUsuarioRolChoicesTest(TestCase):
    """PerfilUsuario.Rol.choices contiene admin y veterinario.

    Valida: Requisito 1.2
    """

    def test_choices_contiene_admin(self):
        valores = [valor for valor, _ in PerfilUsuario.Rol.choices]
        self.assertIn("admin", valores)

    def test_choices_contiene_veterinario(self):
        valores = [valor for valor, _ in PerfilUsuario.Rol.choices]
        self.assertIn("veterinario", valores)

    def test_choices_tiene_exactamente_dos_opciones(self):
        self.assertEqual(len(PerfilUsuario.Rol.choices), 2)
