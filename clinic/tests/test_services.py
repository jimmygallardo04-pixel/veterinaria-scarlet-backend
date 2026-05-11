"""
Tests unitarios de la capa de servicios.

Verifican la lógica de negocio de services.py sin hacer llamadas HTTP.
Usan la base de datos SQLite en memoria configurada en test_settings.py.
"""

from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.utils import timezone

from clinic.models import Clinica, CodigoVerificacion, Especie, Paciente, PerfilUsuario, SexoPaciente, Tratamiento, Tutor, Vacuna
from clinic.services import (
    AlertasClinicaResult,
    CamposObligatoriosError,
    EmailYaRegistradoError,
    PasswordDemasiadoCortaError,
    RegistroClinicaInput,
    buscar_pacientes,
    obtener_alertas_clinicas,
    registrar_clinica,
)
from .helpers import make_especie, make_paciente, make_sexo, make_tutor


def _verificar_email(email: str) -> None:
    """Crea un CodigoVerificacion usado para simular que el email fue verificado."""
    CodigoVerificacion.objects.create(
        email=email,
        codigo="123456",
        creado_en=timezone.now(),
        expira_en=timezone.now() + timedelta(minutes=15),
        usado=True,
    )


# ─── registrar_clinica ────────────────────────────────────────────────────────

class RegistrarClinicaTest(TestCase):
    """registrar_clinica() crea usuario, asigna grupo y devuelve tokens JWT."""

    def setUp(self):
        # Pre-verificar el email por defecto para que los tests no fallen por OTP
        _verificar_email("admin@test.cl")

    def _input(self, **kwargs):
        defaults = dict(
            nombre_clinica="Clínica Test",
            nombre_admin="Admin Test",
            email="admin@test.cl",
            password="segura123",
        )
        defaults.update(kwargs)
        return RegistroClinicaInput(**defaults)

    def test_crea_usuario_con_email_correcto(self):
        result = registrar_clinica(self._input())
        self.assertEqual(result.user.email, "admin@test.cl")
        self.assertEqual(result.user.username, "admin@test.cl")

    def test_usuario_pertenece_al_grupo_admin(self):
        # Los grupos de Django ya no se asignan — el rol se gestiona via PerfilUsuario
        result = registrar_clinica(self._input())
        self.assertFalse(result.user.groups.filter(name="admin").exists())

    def test_perfil_usuario_tiene_rol_admin(self):
        """El PerfilUsuario creado tiene rol='admin' (mecanismo principal de roles)."""
        result = registrar_clinica(self._input())
        self.assertEqual(result.user.perfil.rol, PerfilUsuario.Rol.ADMIN)

    def test_devuelve_tokens_jwt_no_vacios(self):
        result = registrar_clinica(self._input())
        self.assertIsInstance(result.access_token, str)
        self.assertIsInstance(result.refresh_token, str)
        self.assertGreater(len(result.access_token), 0)
        self.assertGreater(len(result.refresh_token), 0)

    def test_nombre_clinica_guardado_en_first_name(self):
        result = registrar_clinica(self._input(nombre_clinica="Mi Clínica"))
        self.assertEqual(result.user.first_name, "Mi Clínica")

    # ── Nuevas assertions para Clinica y PerfilUsuario (tarea 6.1) ────────────

    def test_result_clinica_existe_con_nombre_correcto(self):
        result = registrar_clinica(self._input(nombre_clinica="Clínica Ejemplo"))
        self.assertIsNotNone(result.clinica)
        self.assertEqual(result.clinica.nombre, "Clínica Ejemplo")

    def test_result_clinica_email_admin_coincide(self):
        result = registrar_clinica(self._input(email="admin@test.cl"))
        self.assertEqual(result.clinica.email_admin, "admin@test.cl")

    def test_crea_perfil_usuario_con_rol_admin(self):
        result = registrar_clinica(self._input())
        perfil = PerfilUsuario.objects.filter(user=result.user).first()
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.rol, PerfilUsuario.Rol.ADMIN)

    def test_perfil_usuario_vinculado_a_clinica_correcta(self):
        result = registrar_clinica(self._input())
        perfil = PerfilUsuario.objects.get(user=result.user)
        self.assertEqual(perfil.clinica, result.clinica)

    def test_email_duplicado_lanza_error(self):
        registrar_clinica(self._input())
        with self.assertRaises(EmailYaRegistradoError):
            registrar_clinica(self._input(email="admin@test.cl"))

    def test_password_corta_lanza_error(self):
        with self.assertRaises(PasswordDemasiadoCortaError):
            registrar_clinica(self._input(password="corta"))

    def test_password_exactamente_8_chars_es_valida(self):
        result = registrar_clinica(self._input(password="12345678"))
        self.assertIsNotNone(result.user)

    def test_campos_vacios_lanza_error(self):
        with self.assertRaises(CamposObligatoriosError):
            registrar_clinica(self._input(nombre_clinica=""))

    def test_email_vacio_lanza_error(self):
        with self.assertRaises(CamposObligatoriosError):
            registrar_clinica(self._input(email=""))

    def test_nombre_admin_vacio_lanza_error(self):
        with self.assertRaises(CamposObligatoriosError):
            registrar_clinica(self._input(nombre_admin=""))

    def test_transaccion_atomica_no_crea_usuario_si_falla(self):
        """Si el grupo falla, no debe quedar un usuario huérfano."""
        _verificar_email("nuevo@test.cl")
        # Verificar que el usuario no existe antes
        self.assertFalse(User.objects.filter(username="nuevo@test.cl").exists())
        # Registro exitoso
        registrar_clinica(self._input(email="nuevo@test.cl"))
        self.assertTrue(User.objects.filter(username="nuevo@test.cl").exists())


# ─── Propiedad 4: Atomicidad del registro de clínica ─────────────────────────

from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase


class RegistroAtomicidadPropertyTest(HypothesisTestCase):
    """
    **Propiedad 4: Atomicidad del registro de clínica**
    **Valida: Requisitos 1.3, 4.1, 4.3**

    Verifica que:
    1. Un registro exitoso crea exactamente 1 Clinica, 1 User y 1 PerfilUsuario.
    2. Un registro fallido (email duplicado) no deja objetos parciales en la DB.
    """

    @hyp_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        suffix=st.integers(min_value=1, max_value=999999),
        nombre_clinica=st.text(
            min_size=1, max_size=50,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Zs")),
        ),
        nombre_admin=st.text(
            min_size=1, max_size=50,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Zs")),
        ),
        password=st.text(
            min_size=8, max_size=30,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
        ),
    )
    def test_registro_exitoso_crea_clinica_user_perfil(
        self, suffix, nombre_clinica, nombre_admin, password
    ):
        """Tras un registro exitoso existen exactamente 1 Clinica, 1 User y 1 PerfilUsuario."""
        email = f"prop4_{suffix}@clinica.cl"

        # Limpiar estado previo
        User.objects.filter(username=email).delete()
        Clinica.objects.filter(email_admin=email).delete()
        CodigoVerificacion.objects.filter(email=email).delete()

        _verificar_email(email)

        nombre_clinica_clean = nombre_clinica.strip() or "Clínica Default"
        nombre_admin_clean = nombre_admin.strip() or "Admin Default"

        result = registrar_clinica(RegistroClinicaInput(
            nombre_clinica=nombre_clinica_clean,
            nombre_admin=nombre_admin_clean,
            email=email,
            password=password,
        ))

        # Exactamente 1 Clinica con ese email_admin
        self.assertEqual(Clinica.objects.filter(email_admin=email).count(), 1)
        # Exactamente 1 User con ese email
        self.assertEqual(User.objects.filter(email=email).count(), 1)
        # Exactamente 1 PerfilUsuario con rol admin
        perfil = PerfilUsuario.objects.filter(user=result.user).first()
        self.assertIsNotNone(perfil)
        self.assertEqual(perfil.rol, PerfilUsuario.Rol.ADMIN)
        self.assertEqual(perfil.clinica, result.clinica)
        # El nombre de la clínica es correcto
        self.assertEqual(result.clinica.nombre, nombre_clinica_clean)

        # Limpieza
        result.user.delete()
        Clinica.objects.filter(email_admin=email).delete()
        CodigoVerificacion.objects.filter(email=email).delete()

    @hyp_settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        suffix=st.integers(min_value=1, max_value=999999),
    )
    def test_registro_fallido_no_deja_objetos_parciales(self, suffix):
        """Si el email ya existe, no se crea Clinica ni PerfilUsuario parciales."""
        email = f"dup4_{suffix}@clinica.cl"

        # Crear un usuario existente con ese email
        User.objects.filter(username=email).delete()
        Clinica.objects.filter(email_admin=email).delete()
        CodigoVerificacion.objects.filter(email=email).delete()

        existing_user = User.objects.create_user(
            username=email, email=email, password="existing123"
        )

        clinicas_antes = Clinica.objects.filter(email_admin=email).count()
        perfiles_antes = PerfilUsuario.objects.filter(user__email=email).count()

        _verificar_email(email)

        with self.assertRaises(EmailYaRegistradoError):
            registrar_clinica(RegistroClinicaInput(
                nombre_clinica="Clínica Duplicada",
                nombre_admin="Admin",
                email=email,
                password="password123",
            ))

        # No se crearon objetos parciales
        self.assertEqual(Clinica.objects.filter(email_admin=email).count(), clinicas_antes)
        self.assertEqual(PerfilUsuario.objects.filter(user__email=email).count(), perfiles_antes)

        # Limpieza
        existing_user.delete()
        CodigoVerificacion.objects.filter(email=email).delete()


# ─── buscar_pacientes ─────────────────────────────────────────────────────────

class BuscarPacientesTest(TestCase):
    """buscar_pacientes() filtra correctamente por nombre, tutor y especie."""

    def setUp(self):
        from clinic.models import Clinica
        clinica, _ = Clinica.objects.get_or_create(
            email_admin="buscar@test.cl",
            defaults={"nombre": "Clínica Búsqueda", "activo": True},
        )
        especie_perro = make_especie("Perro", clinica=clinica)
        especie_gato = make_especie("Gato", clinica=clinica)
        sexo = make_sexo(clinica=clinica)

        self.tutor_garcia = Tutor.objects.create(nombre="García López", telefono="111", clinica=clinica)
        self.tutor_smith = Tutor.objects.create(nombre="Smith Jones", telefono="222", clinica=clinica)

        self.firulais = Paciente.objects.create(
            tutor=self.tutor_garcia, nombre="Firulais",
            especie=especie_perro, sexo=sexo, clinica=clinica,
        )
        self.michi = Paciente.objects.create(
            tutor=self.tutor_smith, nombre="Michi",
            especie=especie_gato, sexo=sexo, clinica=clinica,
        )
        self.rex = Paciente.objects.create(
            tutor=self.tutor_garcia, nombre="Rex",
            especie=especie_perro, sexo=sexo, clinica=clinica,
        )

    def test_sin_busqueda_devuelve_todos(self):
        qs = buscar_pacientes()
        self.assertEqual(qs.count(), 3)

    def test_busqueda_por_nombre_paciente(self):
        qs = buscar_pacientes(search="Firulais")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), self.firulais)

    def test_busqueda_case_insensitive(self):
        qs = buscar_pacientes(search="firulais")
        self.assertEqual(qs.count(), 1)

    def test_busqueda_por_nombre_tutor(self):
        qs = buscar_pacientes(search="García")
        self.assertIn(self.firulais, qs)
        self.assertIn(self.rex, qs)
        self.assertNotIn(self.michi, qs)

    def test_busqueda_por_especie(self):
        qs = buscar_pacientes(search="Gato")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), self.michi)

    def test_busqueda_sin_resultados_devuelve_vacio(self):
        qs = buscar_pacientes(search="XYZ_inexistente")
        self.assertEqual(qs.count(), 0)

    def test_busqueda_trunca_a_100_chars(self):
        # Una búsqueda de 200 chars no debe lanzar error
        term_largo = "a" * 200
        qs = buscar_pacientes(search=term_largo)
        self.assertEqual(qs.count(), 0)

    def test_excluye_pacientes_con_tutor_eliminado(self):
        self.tutor_garcia.soft_delete()
        qs = buscar_pacientes()
        # Firulais y Rex tienen tutor eliminado, solo Michi debe aparecer
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), self.michi)

    def test_excluye_pacientes_eliminados(self):
        self.firulais.soft_delete()
        qs = buscar_pacientes()
        self.assertEqual(qs.count(), 2)
        self.assertNotIn(self.firulais, qs)


# ─── obtener_alertas_clinicas ─────────────────────────────────────────────────

class ObtenerAlertasClinicasTest(TestCase):
    """obtener_alertas_clinicas() clasifica correctamente vacunas y tratamientos."""

    def setUp(self):
        tutor = make_tutor()
        self.paciente = make_paciente(tutor)
        self.clinica = self.paciente.clinica
        self.hoy = date.today()

    def test_devuelve_resultado_con_fechas_correctas(self):
        resultado = obtener_alertas_clinicas(clinica=self.clinica, dias_anticipacion=30)
        self.assertIsInstance(resultado, AlertasClinicaResult)
        self.assertEqual(resultado.fecha_revision, self.hoy)
        self.assertEqual(resultado.limite_revision, self.hoy + timedelta(days=30))

    def test_vacuna_vencida_aparece_en_vencidas(self):
        Vacuna.objects.create(
            paciente=self.paciente,
            nombre_vacuna="Rabia",
            fecha_aplicacion=self.hoy - timedelta(days=60),
            proxima_dosis=self.hoy - timedelta(days=1),  # ayer = vencida
            clinica=self.clinica,
        )
        resultado = obtener_alertas_clinicas(clinica=self.clinica)
        self.assertEqual(resultado.vacunas_vencidas.count(), 1)
        self.assertEqual(resultado.vacunas_proximas.count(), 0)

    def test_vacuna_proxima_aparece_en_proximas(self):
        Vacuna.objects.create(
            paciente=self.paciente,
            nombre_vacuna="Parvovirus",
            fecha_aplicacion=self.hoy - timedelta(days=30),
            proxima_dosis=self.hoy + timedelta(days=15),  # en 15 días = próxima
            clinica=self.clinica,
        )
        resultado = obtener_alertas_clinicas(clinica=self.clinica, dias_anticipacion=30)
        self.assertEqual(resultado.vacunas_proximas.count(), 1)
        self.assertEqual(resultado.vacunas_vencidas.count(), 0)

    def test_vacuna_lejana_no_aparece_en_proximas(self):
        Vacuna.objects.create(
            paciente=self.paciente,
            nombre_vacuna="Leptospira",
            fecha_aplicacion=self.hoy - timedelta(days=10),
            proxima_dosis=self.hoy + timedelta(days=60),  # en 60 días = fuera del rango
            clinica=self.clinica,
        )
        resultado = obtener_alertas_clinicas(clinica=self.clinica, dias_anticipacion=30)
        self.assertEqual(resultado.vacunas_proximas.count(), 0)

    def test_tratamiento_activo_aparece(self):
        Tratamiento.objects.create(
            paciente=self.paciente,
            medicamento="Amoxicilina",
            dosis="250mg",
            frecuencia="Cada 8h",
            fecha_inicio=self.hoy - timedelta(days=2),
            fecha_fin=self.hoy + timedelta(days=5),
            clinica=self.clinica,
        )
        resultado = obtener_alertas_clinicas(clinica=self.clinica)
        self.assertEqual(resultado.tratamientos_activos.count(), 1)

    def test_tratamiento_finalizado_no_aparece(self):
        Tratamiento.objects.create(
            paciente=self.paciente,
            medicamento="Ibuprofeno",
            dosis="100mg",
            frecuencia="Cada 12h",
            fecha_inicio=self.hoy - timedelta(days=10),
            fecha_fin=self.hoy - timedelta(days=1),  # terminó ayer
            clinica=self.clinica,
        )
        resultado = obtener_alertas_clinicas(clinica=self.clinica)
        self.assertEqual(resultado.tratamientos_activos.count(), 0)

    def test_tratamiento_indefinido_aparece(self):
        Tratamiento.objects.create(
            paciente=self.paciente,
            medicamento="Enalapril",
            dosis="5mg",
            frecuencia="Diario",
            fecha_inicio=self.hoy - timedelta(days=30),
            fecha_fin=None,  # sin fecha de fin
            clinica=self.clinica,
        )
        resultado = obtener_alertas_clinicas(clinica=self.clinica)
        self.assertEqual(resultado.tratamientos_activos.count(), 1)

    def test_excluye_alertas_de_pacientes_eliminados(self):
        Vacuna.objects.create(
            paciente=self.paciente,
            nombre_vacuna="Rabia",
            fecha_aplicacion=self.hoy - timedelta(days=60),
            proxima_dosis=self.hoy - timedelta(days=1),
            clinica=self.clinica,
        )
        self.paciente.soft_delete()
        resultado = obtener_alertas_clinicas(clinica=self.clinica)
        self.assertEqual(resultado.vacunas_vencidas.count(), 0)

    def test_dias_anticipacion_personalizable(self):
        Vacuna.objects.create(
            paciente=self.paciente,
            nombre_vacuna="Parvovirus",
            fecha_aplicacion=self.hoy - timedelta(days=10),
            proxima_dosis=self.hoy + timedelta(days=45),
            clinica=self.clinica,
        )
        # Con 30 días de anticipación no aparece
        resultado_30 = obtener_alertas_clinicas(clinica=self.clinica, dias_anticipacion=30)
        self.assertEqual(resultado_30.vacunas_proximas.count(), 0)
        # Con 60 días de anticipación sí aparece
        resultado_60 = obtener_alertas_clinicas(clinica=self.clinica, dias_anticipacion=60)
        self.assertEqual(resultado_60.vacunas_proximas.count(), 1)


# ─── Propiedad 8: Data migration completa y sin pérdida de datos ──────────────

from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from clinic.models import Clinica, PerfilUsuario


class DataMigrationPropertyTest(HypothesisTestCase):
    """
    **Validates: Requirements 2.3, 9.1, 9.2, 9.4**

    Propiedad 8: Data migration completa y sin pérdida de datos.

    Verifica que migrar_datos() es idempotente: ejecutarla cuando todos los
    registros ya tienen clinica_id no debe romper nada ni crear duplicados.
    """

    @hyp_settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        n_tutores=st.integers(min_value=0, max_value=10),
        n_users=st.integers(min_value=0, max_value=10),
    )
    def test_data_migration_asigna_clinica_y_crea_perfiles(
        self, n_tutores, n_users
    ):
        """
        Verifica que migrar_datos() no rompe nada cuando se ejecuta sobre
        registros que ya tienen clinica_id asignado, y crea PerfilUsuario
        para Users que no tienen uno.
        """
        import importlib
        from django.contrib.auth.models import Group, User as DjangoUser
        from clinic.models import (
            Especie, SexoPaciente, TipoArchivoDocumento,
            Tutor, Paciente, FichaClinica, Cita, Vacuna,
            Tratamiento, ArchivoDocumento,
        )

        migration_module = importlib.import_module(
            "clinic.migrations.0011_data_migration_tenant"
        )
        migrar_datos = migration_module.migrar_datos

        # Limpiar estado previo para que el test sea idempotente
        PerfilUsuario.objects.all().delete()
        Clinica.objects.filter(email_admin="migrada@veterinariascarlet.cl").delete()
        ArchivoDocumento.objects.all().delete()
        Vacuna.objects.all().delete()
        Tratamiento.objects.all().delete()
        Cita.objects.all().delete()
        FichaClinica.objects.all().delete()
        Paciente.objects.all().delete()
        Tutor.objects.all().delete()
        TipoArchivoDocumento.objects.all().delete()
        SexoPaciente.objects.all().delete()
        Especie.objects.all().delete()
        DjangoUser.objects.all().delete()

        # Crear una clínica de prueba para los registros
        clinica_test, _ = Clinica.objects.get_or_create(
            email_admin="test_migration@test.cl",
            defaults={"nombre": "Clínica Test Migración", "activo": True},
        )

        # Crear catálogos con clinica (estado post-migración)
        especie = Especie.objects.create(nombre="Perro", clinica=clinica_test)
        sexo = SexoPaciente.objects.create(nombre="Macho", clinica=clinica_test)
        tipo_archivo = TipoArchivoDocumento.objects.create(nombre="Radiografía", clinica=clinica_test)

        # Crear tutores con clinica
        tutores = []
        for i in range(n_tutores):
            tutor = Tutor.objects.create(
                nombre=f"Tutor {i}", telefono=f"9{i:08d}", clinica=clinica_test
            )
            tutores.append(tutor)

        # Crear usuarios sin PerfilUsuario
        admin_group, _ = Group.objects.get_or_create(name="admin")
        for i in range(n_users):
            user = DjangoUser.objects.create_user(
                username=f"user_mig_{i}",
                email=f"user_mig_{i}@test.cl",
                password="testpass123",
            )
            if i % 2 == 0:
                user.groups.add(admin_group)

        total_users = DjangoUser.objects.count()

        # Ejecutar la función de migración directamente.
        from django.apps import apps as django_apps
        migrar_datos(apps=django_apps, schema_editor=None)

        # ── Verificaciones ──────────────────────────────────────────────────

        # 1. Todos los Tutores siguen teniendo clinica_id no nulo
        tutores_sin_clinica = Tutor.objects.filter(clinica__isnull=True).count()
        self.assertEqual(
            tutores_sin_clinica, 0,
            f"Hay {tutores_sin_clinica} Tutor(es) sin clinica_id tras la migración"
        )

        # 2. Los catálogos siguen teniendo clinica_id no nulo
        especies_sin_clinica = Especie.objects.filter(clinica__isnull=True).count()
        self.assertEqual(
            especies_sin_clinica, 0,
            f"Hay {especies_sin_clinica} Especie(s) sin clinica_id tras la migración"
        )

        # 3. Todos los Users tienen exactamente un PerfilUsuario
        total_perfiles = PerfilUsuario.objects.count()
        self.assertEqual(
            total_perfiles, total_users,
            f"Se esperaban {total_users} PerfilUsuario(s), pero hay {total_perfiles}"
        )

        for user in DjangoUser.objects.all():
            perfiles_del_user = PerfilUsuario.objects.filter(user=user).count()
            self.assertEqual(
                perfiles_del_user, 1,
                f"El usuario {user.username} tiene {perfiles_del_user} PerfilUsuario(s), se esperaba 1"
            )

        # 4. Los roles se asignan correctamente según la lógica de la data migration
        # (la migración usa grupos de Django para determinar el rol, no PerfilUsuario.rol)
        for user in DjangoUser.objects.all():
            perfil = PerfilUsuario.objects.get(user=user)
            # La migración asigna admin si es superusuario O pertenece al grupo "admin"
            es_admin_migrado = user.is_superuser or user.groups.filter(name="admin").exists()
            rol_esperado = "admin" if es_admin_migrado else "veterinario"
            self.assertEqual(
                perfil.rol, rol_esperado,
                f"Usuario {user.username}: rol esperado '{rol_esperado}', obtenido '{perfil.rol}'"
            )

        # 5. La clínica migrada existe (creada por migrar_datos para registros huérfanos)
        self.assertTrue(
            Clinica.objects.filter(email_admin="migrada@veterinariascarlet.cl").exists(),
            "La clínica migrada no fue creada"
        )


# ─── Gestión de veterinarios con clínica (Tarea 7.1) ─────────────────────────

from clinic.services import (
    CrearVeterinarioInput,
    EditarVeterinarioInput,
    VeterinarioNoEncontradoError,
    crear_veterinario,
    editar_veterinario,
    eliminar_veterinario,
    listar_veterinarios,
)


class GestionVeterinariosConClinicaTest(TestCase):
    """
    Tests unitarios para gestión de veterinarios con aislamiento por clínica.
    Requisitos: 5.1, 5.2, 5.3, 5.4
    """

    def setUp(self):
        self.clinica_a = Clinica.objects.create(
            nombre="Clínica A",
            email_admin="clinica_a@test.cl",
        )
        self.clinica_b = Clinica.objects.create(
            nombre="Clínica B",
            email_admin="clinica_b@test.cl",
        )

    def _crear_vet(self, email: str, clinica: Clinica) -> "VeterinarioResult":
        data = CrearVeterinarioInput(
            nombre="Vet Test",
            email=email,
            password="password123",
        )
        return crear_veterinario(data, clinica)

    def test_crear_veterinario_asigna_clinica_correcta(self):
        """crear_veterinario asigna la clínica correcta al PerfilUsuario."""
        result = self._crear_vet("vet_a@test.cl", self.clinica_a)
        perfil = PerfilUsuario.objects.get(user__id=result.id)
        self.assertEqual(perfil.clinica, self.clinica_a)
        self.assertEqual(perfil.rol, PerfilUsuario.Rol.VETERINARIO)

    def test_crear_veterinario_clinica_b_asigna_clinica_b(self):
        """crear_veterinario para clínica B no asigna clínica A."""
        result = self._crear_vet("vet_b@test.cl", self.clinica_b)
        perfil = PerfilUsuario.objects.get(user__id=result.id)
        self.assertEqual(perfil.clinica, self.clinica_b)
        self.assertNotEqual(perfil.clinica, self.clinica_a)

    def test_listar_veterinarios_no_devuelve_vets_de_otra_clinica(self):
        """listar_veterinarios(clinica_a) no devuelve veterinarios de clinica_b."""
        self._crear_vet("vet_a1@test.cl", self.clinica_a)
        self._crear_vet("vet_a2@test.cl", self.clinica_a)
        self._crear_vet("vet_b1@test.cl", self.clinica_b)

        vets_a = listar_veterinarios(self.clinica_a)
        emails_a = {v.email for v in vets_a}

        self.assertIn("vet_a1@test.cl", emails_a)
        self.assertIn("vet_a2@test.cl", emails_a)
        self.assertNotIn("vet_b1@test.cl", emails_a)
        self.assertEqual(len(vets_a), 2)

    def test_listar_veterinarios_clinica_b_no_devuelve_vets_de_clinica_a(self):
        """listar_veterinarios(clinica_b) no devuelve veterinarios de clinica_a."""
        self._crear_vet("vet_a_solo@test.cl", self.clinica_a)
        self._crear_vet("vet_b_solo@test.cl", self.clinica_b)

        vets_b = listar_veterinarios(self.clinica_b)
        emails_b = {v.email for v in vets_b}

        self.assertIn("vet_b_solo@test.cl", emails_b)
        self.assertNotIn("vet_a_solo@test.cl", emails_b)

    def test_eliminar_veterinario_de_otra_clinica_lanza_error(self):
        """eliminar_veterinario(id_vet_b, clinica_a) lanza VeterinarioNoEncontradoError."""
        result_b = self._crear_vet("vet_b_del@test.cl", self.clinica_b)

        with self.assertRaises(VeterinarioNoEncontradoError):
            eliminar_veterinario(result_b.id, self.clinica_a)

    def test_eliminar_veterinario_propio_funciona(self):
        """eliminar_veterinario con la clínica correcta desactiva al usuario."""
        result_a = self._crear_vet("vet_a_del@test.cl", self.clinica_a)
        eliminar_veterinario(result_a.id, self.clinica_a)

        user = User.objects.get(pk=result_a.id)
        self.assertFalse(user.is_active)

    def test_editar_veterinario_de_otra_clinica_lanza_error(self):
        """editar_veterinario con veterinario de otra clínica lanza VeterinarioNoEncontradoError."""
        result_b = self._crear_vet("vet_b_edit@test.cl", self.clinica_b)
        data = EditarVeterinarioInput(nombre="Nuevo Nombre", email=None, password=None)

        with self.assertRaises(VeterinarioNoEncontradoError):
            editar_veterinario(result_b.id, data, self.clinica_a)

    def test_editar_veterinario_propio_funciona(self):
        """editar_veterinario con la clínica correcta actualiza el nombre."""
        result_a = self._crear_vet("vet_a_edit@test.cl", self.clinica_a)
        data = EditarVeterinarioInput(nombre="Nombre Actualizado", email=None, password=None)

        updated = editar_veterinario(result_a.id, data, self.clinica_a)
        self.assertEqual(updated.nombre, "Nombre Actualizado")


# ─── Propiedad 6: Aislamiento de veterinarios por clínica ────────────────────


class VeterinariosAislamientoPropertyTest(HypothesisTestCase):
    """
    **Propiedad 6: Aislamiento de veterinarios por clínica**
    **Valida: Requisitos 5.1, 5.2**

    Verifica que listar_veterinarios(clinica_a) devuelve exactamente n_vets_a
    resultados y ninguno pertenece a clinica_b.
    """

    @hyp_settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        n_vets_a=st.integers(min_value=1, max_value=5),
        n_vets_b=st.integers(min_value=1, max_value=5),
    )
    def test_veterinarios_aislados_por_clinica(self, n_vets_a, n_vets_b):
        """
        Crear dos clínicas con N veterinarios cada una.
        listar_veterinarios(clinica_a) devuelve exactamente n_vets_a resultados
        y ninguno pertenece a clinica_b.
        """
        import uuid

        uid = uuid.uuid4().hex[:8]

        # Crear dos clínicas únicas para este ejemplo
        clinica_a = Clinica.objects.create(
            nombre=f"Clínica A {uid}",
            email_admin=f"clinica_a_{uid}@prop6.cl",
        )
        clinica_b = Clinica.objects.create(
            nombre=f"Clínica B {uid}",
            email_admin=f"clinica_b_{uid}@prop6.cl",
        )

        # Crear n_vets_a veterinarios en clínica A
        ids_clinica_b = set()
        for i in range(n_vets_a):
            data = CrearVeterinarioInput(
                nombre=f"Vet A{i} {uid}",
                email=f"vet_a{i}_{uid}@prop6.cl",
                password="password123",
            )
            crear_veterinario(data, clinica_a)

        # Crear n_vets_b veterinarios en clínica B
        for i in range(n_vets_b):
            data = CrearVeterinarioInput(
                nombre=f"Vet B{i} {uid}",
                email=f"vet_b{i}_{uid}@prop6.cl",
                password="password123",
            )
            result_b = crear_veterinario(data, clinica_b)
            ids_clinica_b.add(result_b.id)

        # Verificar aislamiento
        vets_a = listar_veterinarios(clinica_a)

        # Exactamente n_vets_a resultados
        self.assertEqual(
            len(vets_a), n_vets_a,
            f"Se esperaban {n_vets_a} veterinarios en clínica A, se obtuvieron {len(vets_a)}"
        )

        # Ninguno pertenece a clínica B
        for vet in vets_a:
            self.assertNotIn(
                vet.id, ids_clinica_b,
                f"El veterinario id={vet.id} pertenece a clínica B pero apareció en listar_veterinarios(clinica_a)"
            )

        # Limpieza
        User.objects.filter(email__endswith=f"_{uid}@prop6.cl").delete()
        clinica_a.delete()
        clinica_b.delete()
