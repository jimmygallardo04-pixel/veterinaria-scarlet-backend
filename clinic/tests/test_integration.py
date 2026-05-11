"""
Tests de integración HTTP con Hypothesis (property-based testing).

Todos los endpoints usan el prefijo /api/v1/.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase
from rest_framework.test import APIClient

from django.db import IntegrityError, transaction

from clinic.models import Cita, Clinica, CodigoVerificacion, Especie, Paciente, PerfilUsuario, SexoPaciente, Tutor
from .helpers import make_cita, make_clinica, make_paciente, make_tutor, make_user


# ─── Propiedad 3: Filtrado de citas por paciente ──────────────────────────────

class CitaFiltradoPorPacienteTest(HypothesisTestCase):
    """
    GET /api/v1/citas/?paciente={id} devuelve únicamente citas del paciente
    indicado. Si el id no existe, devuelve lista vacía con HTTP 200.
    """

    def setUp(self):
        self.client = APIClient()
        self.clinica = make_clinica("Clínica Citas Test")
        self.user = make_user(clinica=self.clinica)
        self.client.force_authenticate(user=self.user)

    @hyp_settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        n_pacientes=st.integers(min_value=2, max_value=5),
        citas_por_paciente=st.lists(
            st.integers(min_value=0, max_value=4),
            min_size=2,
            max_size=5,
        ),
    )
    def test_filtrado_devuelve_solo_citas_del_paciente(self, n_pacientes, citas_por_paciente):
        Cita.objects.all().delete()
        Paciente.objects.all().delete()
        Tutor.objects.all().delete()

        while len(citas_por_paciente) < n_pacientes:
            citas_por_paciente.append(0)

        pacientes_creados = []
        for i in range(n_pacientes):
            tutor = make_tutor(nombre=f"Tutor {i}", telefono=f"9000000{i}", clinica=self.clinica)
            paciente = make_paciente(tutor, nombre=f"Paciente {i}", clinica=self.clinica)
            for j in range(citas_por_paciente[i]):
                make_cita(paciente, tutor, motivo=f"Motivo {i}-{j}", clinica=self.clinica)
            pacientes_creados.append(paciente)

        for paciente in pacientes_creados:
            response = self.client.get(f"/api/v1/citas/?paciente={paciente.id}")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            citas = data["results"] if "results" in data else data

            for cita in citas:
                self.assertEqual(cita["paciente"], paciente.id)

            expected = Cita.objects.filter(
                paciente=paciente, eliminado_en__isnull=True
            ).count()
            self.assertEqual(len(citas), expected)

    @hyp_settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(nonexistent_id=st.integers(min_value=999000, max_value=999999))
    def test_id_inexistente_devuelve_lista_vacia(self, nonexistent_id):
        Paciente.objects.filter(id=nonexistent_id).delete()
        response = self.client.get(f"/api/v1/citas/?paciente={nonexistent_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data["results"] if "results" in data else data
        self.assertEqual(results, [])


# ─── Propiedad 8: Tamaño de página respeta el límite ─────────────────────────

class TamanoPaginaTest(HypothesisTestCase):
    """
    GET /api/v1/pacientes/?page_size={n} devuelve como máximo min(n, 100) registros.
    """

    def setUp(self):
        self.client = APIClient()
        self.clinica = make_clinica("Clínica Paginacion Test")
        self.user = make_user(username="testuser_p8", clinica=self.clinica)
        self.client.force_authenticate(user=self.user)

    @hyp_settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        page_size=st.integers(min_value=1, max_value=200),
        n_pacientes=st.integers(min_value=0, max_value=50),
    )
    def test_results_no_excede_min_page_size_100(self, page_size, n_pacientes):
        Paciente.objects.all().delete()
        Tutor.objects.all().delete()

        for i in range(n_pacientes):
            tutor = make_tutor(nombre=f"Tutor P8 {i}", telefono=f"8000000{i}", clinica=self.clinica)
            make_paciente(tutor, nombre=f"Paciente P8 {i}", clinica=self.clinica)

        response = self.client.get(f"/api/v1/pacientes/?page_size={page_size}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)

        max_expected = min(page_size, 100)
        self.assertLessEqual(len(data["results"]), max_expected)


# ─── Propiedad 9: Paginación completa sin duplicados ─────────────────────────

class PaginacionCompletaTest(HypothesisTestCase):
    """
    Recorrer todas las páginas de /api/v1/pacientes/ cubre todos los registros
    exactamente una vez, sin duplicados ni omisiones.
    """

    def setUp(self):
        self.client = APIClient()
        self.clinica = make_clinica("Clínica Paginacion Completa Test")
        self.user = make_user(username="testuser_p9", clinica=self.clinica)
        self.client.force_authenticate(user=self.user)

    @hyp_settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(n_pacientes=st.integers(min_value=0, max_value=60))
    def test_paginacion_completa_sin_duplicados(self, n_pacientes):
        Paciente.objects.all().delete()
        Tutor.objects.all().delete()

        for i in range(n_pacientes):
            tutor = make_tutor(nombre=f"Tutor P9 {i}", telefono=f"7000000{i}", clinica=self.clinica)
            make_paciente(tutor, nombre=f"Paciente P9 {i}", clinica=self.clinica)

        all_ids = []
        page = 1
        while True:
            response = self.client.get(f"/api/v1/pacientes/?page_size=10&page={page}")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("results", data)
            self.assertIn("count", data)
            self.assertIn("next", data)

            for item in data["results"]:
                all_ids.append(item["id"])

            if data["next"] is None:
                break
            page += 1

        # Sin duplicados
        self.assertEqual(len(all_ids), len(set(all_ids)))

        # Cubre todos los registros de la clínica del usuario
        expected = Paciente.objects.filter(
            clinica=self.clinica,
            eliminado_en__isnull=True,
            tutor__eliminado_en__isnull=True,
        ).count()
        self.assertEqual(len(all_ids), expected)


# ─── Propiedad 10: Metadatos de paginación siempre presentes ─────────────────

class MetadatosPaginacionTest(HypothesisTestCase):
    """
    Toda respuesta paginada incluye count, next, previous y results.
    """

    def setUp(self):
        self.client = APIClient()
        self.clinica = make_clinica("Clínica Metadatos Test")
        self.user = make_user(username="testuser_p10", clinica=self.clinica)
        self.client.force_authenticate(user=self.user)

    @hyp_settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        n_pacientes=st.integers(min_value=0, max_value=45),
        page=st.integers(min_value=1, max_value=3),
    )
    def test_respuesta_paginada_incluye_metadatos(self, n_pacientes, page):
        Paciente.objects.all().delete()
        Tutor.objects.all().delete()

        for i in range(n_pacientes):
            tutor = make_tutor(nombre=f"Tutor P10 {i}", telefono=f"6000000{i}", clinica=self.clinica)
            make_paciente(tutor, nombre=f"Paciente P10 {i}", clinica=self.clinica)

        response = self.client.get(f"/api/v1/pacientes/?page={page}")
        if response.status_code == 404:
            return  # página fuera de rango es válido

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("count", data)
        self.assertIsInstance(data["count"], int)
        self.assertGreaterEqual(data["count"], 0)

        self.assertIn("next", data)
        self.assertTrue(data["next"] is None or isinstance(data["next"], str))

        self.assertIn("previous", data)
        self.assertTrue(data["previous"] is None or isinstance(data["previous"], str))

        self.assertIn("results", data)


# ─── Propiedad 12: Búsqueda devuelve solo resultados que contienen el término ─

class BusquedaGlobalPacientesTest(HypothesisTestCase):
    """
    GET /api/v1/pacientes/?search={term} devuelve solo pacientes cuyo nombre,
    tutor o especie contiene el término (case-insensitive).
    """

    def setUp(self):
        self.client = APIClient()
        self.clinica = make_clinica("Clínica Búsqueda")
        self.user = make_user(username="testuser_p12", clinica=self.clinica)
        self.client.force_authenticate(user=self.user)

    @hyp_settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        search_term=st.text(
            min_size=2,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu")),
        ),
        n_pacientes=st.integers(min_value=1, max_value=10),
    )
    def test_resultados_contienen_termino_buscado(self, search_term, n_pacientes):
        Paciente.objects.all().delete()
        Tutor.objects.all().delete()
        Especie.objects.all().delete()

        clinica = self.clinica
        sexo, _ = SexoPaciente.objects.get_or_create(nombre="Macho", clinica=clinica)

        for i in range(n_pacientes):
            especie, _ = Especie.objects.get_or_create(nombre=f"Especie{i}", clinica=clinica)
            tutor = Tutor.objects.create(nombre=f"Tutor{i}", telefono=f"5000000{i}", clinica=clinica)
            Paciente.objects.create(
                tutor=tutor, nombre=f"Paciente{i}", especie=especie, sexo=sexo, clinica=clinica,
            )

        # Crear un paciente que siempre coincida con el término
        especie_match, _ = Especie.objects.get_or_create(nombre=f"EspecieMatch{search_term[:10]}", clinica=clinica)
        tutor_match = Tutor.objects.create(nombre="TutorMatch", telefono="5999999", clinica=clinica)
        Paciente.objects.create(
            tutor=tutor_match,
            nombre=f"Match{search_term}End",
            especie=especie_match,
            sexo=sexo,
            clinica=clinica,
        )

        response = self.client.get(f"/api/v1/pacientes/?search={search_term}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)

        term_lower = search_term.lower()
        for paciente in data["results"]:
            nombre_match = term_lower in paciente["nombre"].lower()
            tutor_match_flag = term_lower in paciente["tutor_nombre"].lower()
            especie_match_flag = term_lower in paciente["especie_nombre"].lower()
            self.assertTrue(
                nombre_match or tutor_match_flag or especie_match_flag,
                msg=(
                    f"Paciente id={paciente['id']} nombre='{paciente['nombre']}' "
                    f"no contiene el término '{search_term}'"
                ),
            )


# ─── Propiedad 21: Email duplicado → HTTP 400 ─────────────────────────────────

class RegistroEmailDuplicadoTest(HypothesisTestCase):
    """
    POST /api/v1/registro/ con email ya registrado devuelve HTTP 400.
    """

    @hyp_settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        local=st.text(
            min_size=1, max_size=20,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
        ),
        domain=st.sampled_from(["example.com", "test.org", "clinica.cl", "mail.net"]),
    )
    def test_email_duplicado_devuelve_400(self, local, domain):
        email = f"{local}@{domain}"
        User.objects.filter(username=email).delete()
        User.objects.create_user(username=email, email=email, password="existingpass123")

        client = APIClient()
        response = client.post("/api/v1/registro/", {
            "nombre_clinica": "Clínica Test",
            "nombre_admin": "Admin Test",
            "email": email,
            "password": "nuevapass123",
        }, format="json")

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("email", data)
        self.assertIn("Este correo ya está en uso", data["email"])

        User.objects.filter(username=email).delete()


# ─── Propiedad 22: Contraseña corta → HTTP 400 ────────────────────────────────

class RegistroPasswordCortaTest(HypothesisTestCase):
    """
    POST /api/v1/registro/ con contraseña < 8 chars devuelve HTTP 400.
    """

    @hyp_settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        password=st.text(max_size=7),
        suffix=st.integers(min_value=100000, max_value=999999),
    )
    def test_password_corta_devuelve_400(self, password, suffix):
        email = f"pwtest{suffix}@example.com"
        User.objects.filter(username=email).delete()

        client = APIClient()
        response = client.post("/api/v1/registro/", {
            "nombre_clinica": "Clínica Test",
            "nombre_admin": "Admin Test",
            "email": email,
            "password": password,
        }, format="json")

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("password", data)
        self.assertIn("La contraseña debe tener al menos 8 caracteres", data["password"])
        self.assertFalse(User.objects.filter(username=email).exists())


# ─── Propiedad 23: Registro válido crea usuario admin con tokens JWT ──────────

class RegistroValidoCreaAdminTest(HypothesisTestCase):
    """
    POST /api/v1/registro/ con payload válido crea usuario en grupo admin
    y devuelve tokens JWT.
    """

    @hyp_settings(
        max_examples=30,
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
        password_suffix=st.text(
            min_size=1, max_size=20,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
        ),
    )
    def test_registro_valido_crea_usuario_admin(
        self, suffix, nombre_clinica, nombre_admin, password_suffix
    ):
        email = f"valid{suffix}@clinica.cl"
        User.objects.filter(username=email).delete()
        CodigoVerificacion.objects.filter(email=email).delete()

        # Simular que el email fue verificado con OTP antes del registro
        CodigoVerificacion.objects.create(
            email=email,
            codigo="123456",
            creado_en=timezone.now(),
            expira_en=timezone.now() + timedelta(minutes=15),
            usado=True,
        )

        client = APIClient()
        response = client.post("/api/v1/registro/", {
            "nombre_clinica": nombre_clinica.strip() or "Clínica Default",
            "nombre_admin": nombre_admin.strip() or "Admin Default",
            "email": email,
            "password": f"Secure1!{password_suffix}",
        }, format="json")

        self.assertEqual(response.status_code, 201, response.json())
        data = response.json()

        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertIsInstance(data["access"], str)
        self.assertGreater(len(data["access"]), 0)

        self.assertIn("user", data)
        self.assertEqual(data["user"]["email"], email)
        self.assertEqual(data["user"]["rol"], "admin")
        # clinica_id y clinica_nombre deben estar presentes en la respuesta
        self.assertIn("clinica_id", data["user"])
        self.assertIn("clinica_nombre", data["user"])
        self.assertIsNotNone(data["user"]["clinica_id"])
        self.assertEqual(data["user"]["clinica_nombre"], nombre_clinica.strip() or "Clínica Default")

        user = User.objects.filter(username=email).first()
        self.assertIsNotNone(user)
        # Verificar rol mediante PerfilUsuario (mecanismo principal)
        self.assertEqual(user.perfil.rol, "admin")
        # Los grupos de Django ya no se asignan — el rol se gestiona via PerfilUsuario
        self.assertFalse(user.groups.filter(name="admin").exists())

        user.delete()
        CodigoVerificacion.objects.filter(email=email).delete()


# ─── Propiedades 1, 2 y 3: Aislamiento multi-tenant ──────────────────────────

class AislamientoLecturaPropertyTest(HypothesisTestCase):
    """
    Tests de propiedad para las Propiedades 1, 2 y 3 del diseño multi-tenant.

    Propiedad 1: Aislamiento de lectura por tenant.
    Propiedad 2: Aislamiento de escritura — clinica asignada automáticamente.
    Propiedad 3: HTTP 404 en acceso cruzado entre tenants.
    """

    # ── Propiedad 1: Aislamiento de lectura por tenant ────────────────────────
    # Valida: Requisitos 3.1, 6.1, 6.3, 8.1, 10.1, 10.4

    @hyp_settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        n_tutores_a=st.integers(1, 5),
        n_tutores_b=st.integers(1, 5),
    )
    def test_get_devuelve_solo_registros_de_la_clinica(self, n_tutores_a, n_tutores_b):
        """
        **Validates: Requirements 3.1, 6.1, 6.3, 8.1, 10.1, 10.4**

        Propiedad 1: Para cualquier usuario autenticado de la clínica A,
        GET /api/v1/tutores/ devuelve únicamente registros con
        clinica_id == clinica_a.id y el count es exactamente n_tutores_a.
        """
        import uuid
        uid = uuid.uuid4().hex[:8]

        # Crear dos clínicas con sus usuarios admin
        clinica_a = make_clinica(f"Clinica A {uid}")
        clinica_b = make_clinica(f"Clinica B {uid}")

        user_a = make_user(username=f"user_a_{uid}", clinica=clinica_a)
        make_user(username=f"user_b_{uid}", clinica=clinica_b)

        # Limpiar tutores previos de estas clínicas
        Tutor.objects.filter(clinica=clinica_a).delete()
        Tutor.objects.filter(clinica=clinica_b).delete()

        # Crear N tutores en cada clínica
        for i in range(n_tutores_a):
            make_tutor(nombre=f"Tutor A{i} {uid}", telefono=f"1{i:08d}", clinica=clinica_a)
        for i in range(n_tutores_b):
            make_tutor(nombre=f"Tutor B{i} {uid}", telefono=f"2{i:08d}", clinica=clinica_b)

        # Autenticar como usuario de clínica A
        client = APIClient()
        client.force_authenticate(user=user_a)

        # GET /api/v1/tutores/ — debe devolver solo los tutores de clínica A
        response = client.get("/api/v1/tutores/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        tutores = data["results"] if "results" in data else data

        # Todos los resultados deben pertenecer a clínica A
        for tutor in tutores:
            self.assertEqual(
                tutor["clinica"], clinica_a.id,
                msg=(
                    f"Tutor id={tutor['id']} tiene clinica={tutor['clinica']} "
                    f"pero se esperaba clinica_id={clinica_a.id}"
                ),
            )

        # El count debe ser exactamente n_tutores_a
        self.assertEqual(
            len(tutores), n_tutores_a,
            msg=(
                f"Se esperaban {n_tutores_a} tutores de clínica A, "
                f"pero se obtuvieron {len(tutores)}"
            ),
        )

    # ── Propiedad 2: Aislamiento de escritura — clinica asignada automáticamente
    # Valida: Requisitos 3.2, 10.2, 10.3

    @hyp_settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(n_posts=st.integers(1, 5))
    def test_post_asigna_clinica_del_usuario(self, n_posts):
        """
        **Validates: Requirements 3.2, 10.2, 10.3**

        Propiedad 2: Para cualquier usuario autenticado de la clínica A,
        cualquier tutor creado mediante POST /api/v1/tutores/ tiene
        clinica_id == clinica.id, independientemente de si el cliente
        envía o no el campo `clinica` en el body.
        """
        import uuid
        uid = uuid.uuid4().hex[:8]

        clinica = make_clinica(f"Clinica Write {uid}")
        user = make_user(username=f"user_write_{uid}", clinica=clinica)

        # Limpiar tutores previos de esta clínica
        Tutor.objects.filter(clinica=clinica).delete()

        client = APIClient()
        client.force_authenticate(user=user)

        for i in range(n_posts):
            # Alternar: con y sin campo `clinica` en el body
            if i % 2 == 0:
                # Sin campo clinica — debe asignarse automáticamente
                payload = {
                    "nombre": f"Tutor Write {i} {uid}",
                    "telefono": f"3{i:08d}",
                }
            else:
                # Con campo clinica=999 (valor incorrecto) — debe ignorarse
                payload = {
                    "nombre": f"Tutor Write {i} {uid}",
                    "telefono": f"4{i:08d}",
                    "clinica": 999999,
                }

            response = client.post("/api/v1/tutores/", payload, format="json")
            self.assertEqual(
                response.status_code, 201,
                msg=f"POST falló con status {response.status_code}: {response.json()}",
            )

            data = response.json()
            self.assertEqual(
                data["clinica"], clinica.id,
                msg=(
                    f"Tutor creado tiene clinica={data['clinica']} "
                    f"pero se esperaba clinica_id={clinica.id} "
                    f"(payload tenía clinica={payload.get('clinica', 'no enviado')})"
                ),
            )

    # ── Propiedad 3: HTTP 404 en acceso cruzado ───────────────────────────────
    # Valida: Requisitos 3.3, 5.4, 10.4

    @hyp_settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(n_recursos=st.integers(1, 5))
    def test_acceso_directo_otra_clinica_devuelve_404(self, n_recursos):
        """
        **Validates: Requirements 3.3, 5.4, 10.4**

        Propiedad 3: Para cualquier recurso de la clínica B, un usuario
        autenticado de la clínica A que intente acceder mediante
        GET, PATCH o DELETE con el ID exacto del recurso debe recibir HTTP 404.
        """
        import uuid
        uid = uuid.uuid4().hex[:8]

        # Crear dos clínicas con sus usuarios admin
        clinica_a = make_clinica(f"Clinica A 404 {uid}")
        clinica_b = make_clinica(f"Clinica B 404 {uid}")

        user_a = make_user(username=f"user_a_404_{uid}", clinica=clinica_a)
        make_user(username=f"user_b_404_{uid}", clinica=clinica_b)

        # Limpiar tutores previos de estas clínicas
        Tutor.objects.filter(clinica=clinica_a).delete()
        Tutor.objects.filter(clinica=clinica_b).delete()

        # Crear N tutores en clínica B
        tutores_b = []
        for i in range(n_recursos):
            tutor = make_tutor(
                nombre=f"Tutor B 404 {i} {uid}",
                telefono=f"5{i:08d}",
                clinica=clinica_b,
            )
            tutores_b.append(tutor)

        # Autenticar como usuario de clínica A
        client = APIClient()
        client.force_authenticate(user=user_a)

        # Intentar GET, PATCH y DELETE a cada tutor de clínica B
        for tutor_b in tutores_b:
            tutor_id = tutor_b.id

            # GET debe devolver 404
            response_get = client.get(f"/api/v1/tutores/{tutor_id}/")
            self.assertEqual(
                response_get.status_code, 404,
                msg=(
                    f"GET /api/v1/tutores/{tutor_id}/ devolvió "
                    f"{response_get.status_code} en lugar de 404 "
                    f"(tutor pertenece a clínica B, usuario es de clínica A)"
                ),
            )

            # PATCH debe devolver 404
            response_patch = client.patch(
                f"/api/v1/tutores/{tutor_id}/",
                {"nombre": "Intento de modificación"},
                format="json",
            )
            self.assertEqual(
                response_patch.status_code, 404,
                msg=(
                    f"PATCH /api/v1/tutores/{tutor_id}/ devolvió "
                    f"{response_patch.status_code} en lugar de 404"
                ),
            )

            # DELETE debe devolver 404
            response_delete = client.delete(f"/api/v1/tutores/{tutor_id}/")
            self.assertEqual(
                response_delete.status_code, 404,
                msg=(
                    f"DELETE /api/v1/tutores/{tutor_id}/ devolvió "
                    f"{response_delete.status_code} en lugar de 404"
                ),
            )


# ─── Propiedad 5: Invariante de perfil único por usuario ─────────────────────

class PerfilUnicoPropertyTest(HypothesisTestCase):
    """
    Tests de propiedad para la Propiedad 5 del diseño multi-tenant.

    Propiedad 5: Invariante de perfil único por usuario.

    # Feature: multi-tenant-clinicas, Property 5
    """

    @hyp_settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(n_registros=st.integers(min_value=1, max_value=10))
    def test_usuario_tiene_exactamente_un_perfil(self, n_registros):
        """
        **Validates: Requirements 1.4, 1.5**

        Propiedad 5: Para cualquier usuario creado a través del sistema
        (registro de clínica o creación de veterinario), debe existir
        exactamente un PerfilUsuario asociado a ese usuario.
        La restricción OneToOneField garantiza que no pueden existir dos
        perfiles para el mismo usuario.
        """
        import uuid
        uid = uuid.uuid4().hex[:8]

        created_users = []

        # Registrar N clínicas distintas, cada una con un email único
        for i in range(n_registros):
            email = f"perfil_test_{uid}_{i}@clinica.cl"
            # Limpiar datos previos
            from django.contrib.auth.models import User as DjangoUser
            DjangoUser.objects.filter(username=email).delete()

            clinica = Clinica.objects.create(
                nombre=f"Clinica Perfil {uid} {i}",
                email_admin=email,
            )
            user = DjangoUser.objects.create_user(
                username=email,
                email=email,
                password="testpass123",
            )
            PerfilUsuario.objects.create(
                user=user,
                clinica=clinica,
                rol=PerfilUsuario.Rol.ADMIN,
            )
            created_users.append(user)

        # Verificar que cada usuario creado tiene exactamente 1 PerfilUsuario
        for user in created_users:
            perfil_count = PerfilUsuario.objects.filter(user=user).count()
            self.assertEqual(
                perfil_count, 1,
                msg=(
                    f"El usuario {user.username} tiene {perfil_count} perfiles, "
                    f"se esperaba exactamente 1."
                ),
            )

        # Intentar crear un segundo PerfilUsuario para el mismo usuario
        # y verificar que lanza IntegrityError
        if created_users:
            first_user = created_users[0]
            extra_clinica = Clinica.objects.create(
                nombre=f"Clinica Extra {uid}",
                email_admin=f"extra_{uid}@clinica.cl",
            )
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    PerfilUsuario.objects.create(
                        user=first_user,
                        clinica=extra_clinica,
                        rol=PerfilUsuario.Rol.VETERINARIO,
                    )

        # Cleanup
        for user in created_users:
            user.delete()
        Clinica.objects.filter(email_admin__startswith=f"perfil_test_{uid}").delete()
        Clinica.objects.filter(email_admin=f"extra_{uid}@clinica.cl").delete()


# ─── Propiedad 7: Unicidad de catálogos dentro de una clínica, no entre clínicas

class CatalogoUnicidadPropertyTest(HypothesisTestCase):
    """
    Tests de propiedad para la Propiedad 7 del diseño multi-tenant.

    Propiedad 7: Unicidad de catálogos dentro de una clínica, no entre clínicas.

    # Feature: multi-tenant-clinicas, Property 7
    """

    @hyp_settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        nombre=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Ll", "Lu")),
        )
    )
    def test_mismo_nombre_catalogo_en_dos_clinicas(self, nombre):
        """
        **Validates: Requirements 6.4, 6.5**

        Propiedad 7: Para cualquier par de clínicas distintas A y B, es posible
        crear ítems de catálogo (Especie) con el mismo nombre en ambas clínicas
        sin error de unicidad. Sin embargo, dentro de la misma clínica, no pueden
        existir dos ítems del mismo tipo con el mismo nombre.
        """
        import uuid
        uid = uuid.uuid4().hex[:8]

        clinica_a = Clinica.objects.create(
            nombre=f"Clinica Cat A {uid}",
            email_admin=f"cat_a_{uid}@clinica.cl",
        )
        clinica_b = Clinica.objects.create(
            nombre=f"Clinica Cat B {uid}",
            email_admin=f"cat_b_{uid}@clinica.cl",
        )

        try:
            # Limpiar especies previas con este nombre en estas clínicas
            Especie.all_objects.filter(nombre=nombre, clinica=clinica_a).delete()
            Especie.all_objects.filter(nombre=nombre, clinica=clinica_b).delete()

            # Crear Especie con el mismo nombre en ambas clínicas — no debe lanzar error
            especie_a = Especie.objects.create(nombre=nombre, clinica=clinica_a)
            especie_b = Especie.objects.create(nombre=nombre, clinica=clinica_b)

            self.assertEqual(especie_a.nombre, nombre)
            self.assertEqual(especie_b.nombre, nombre)
            self.assertNotEqual(especie_a.clinica_id, especie_b.clinica_id)

            # Intentar crear una segunda Especie con el mismo nombre en la misma clínica
            # debe lanzar IntegrityError
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    Especie.objects.create(nombre=nombre, clinica=clinica_a)

        finally:
            # Cleanup
            Especie.all_objects.filter(clinica__in=[clinica_a, clinica_b]).delete()
            clinica_a.delete()
            clinica_b.delete()
