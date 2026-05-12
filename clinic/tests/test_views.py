"""
Tests unitarios para las vistas de la API.

Cubre el endpoint /me/ con distintos escenarios de usuario.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from clinic.models import Clinica, PerfilUsuario
from .helpers import make_clinica, make_user


class MeViewTest(TestCase):
    """Tests unitarios para GET /api/v1/me/."""

    def setUp(self):
        self.client = APIClient()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get_me(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get("/api/v1/me/")

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_usuario_con_perfil_recibe_clinica_datos(self):
        """Un usuario con PerfilUsuario recibe clinica_id, clinica_nombre y rol correctos."""
        clinica = make_clinica("Clínica Me Test")
        user = make_user(username="me_con_perfil", clinica=clinica)

        response = self._get_me(user)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        perfil = PerfilUsuario.objects.get(user=user)
        self.assertEqual(data["clinica_id"], clinica.id)
        self.assertEqual(data["clinica_nombre"], clinica.nombre)
        self.assertEqual(data["rol"], perfil.rol)

    def test_usuario_sin_perfil_recibe_nulls(self):
        """Un usuario sin PerfilUsuario recibe clinica_id=null y rol=null, sin error 500."""
        user = User.objects.create_user(
            username="me_sin_perfil",
            email="me_sin_perfil@test.cl",
            password="testpass123",
        )

        response = self._get_me(user)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["clinica_id"])
        self.assertIsNone(data["clinica_nombre"])
        self.assertIsNone(data["rol"])

    def test_superusuario_sin_perfil_recibe_rol_superusuario(self):
        """Un superusuario sin PerfilUsuario recibe rol='superusuario' y clinica_id=null."""
        superuser = User.objects.create_superuser(
            username="me_superuser",
            email="me_superuser@test.cl",
            password="superpass123",
        )

        response = self._get_me(superuser)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["rol"], "superusuario")
        self.assertIsNone(data["clinica_id"])
        self.assertIsNone(data["clinica_nombre"])
        self.assertTrue(data["is_superuser"])

    def test_campos_existentes_siguen_presentes(self):
        """Los campos id, email e is_superuser siguen presentes en la respuesta."""
        clinica = make_clinica("Clínica Campos Test")
        user = make_user(username="me_campos", clinica=clinica)
        user.email = "me_campos@test.cl"
        user.save()

        response = self._get_me(user)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("id", data)
        self.assertEqual(data["id"], user.id)
        self.assertIn("email", data)
        self.assertEqual(data["email"], user.email)
        self.assertIn("is_superuser", data)
        self.assertFalse(data["is_superuser"])
        # Verify all expected fields are present (username removido: es igual al email)
        for field in ("id", "email", "first_name", "last_name", "is_superuser", "rol", "clinica_id", "clinica_nombre"):
            self.assertIn(field, data, msg=f"Campo '{field}' ausente en la respuesta de /me/")
        # username ya no se expone (es redundante con email en este sistema)
        self.assertNotIn("username", data)

    def test_unauthenticated_returns_401(self):
        """Un usuario no autenticado recibe HTTP 401."""
        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 401)


class VeterinariosViewTest(TestCase):
    """
    Tests unitarios para GET/POST /api/v1/veterinarios/ y PATCH/DELETE /api/v1/veterinarios/<pk>/.

    Verifica que las vistas obtienen la clínica del perfil del usuario y la pasan
    a los servicios, y que manejan correctamente la ausencia de perfil (HTTP 403).
    """

    def setUp(self):
        self.client = APIClient()
        from django.contrib.auth.models import Group
        admin_group, _ = Group.objects.get_or_create(name="admin")

        # Clínica A con su admin
        self.clinica_a = make_clinica("Clínica A Vets")
        self.admin_a = make_user(username="admin_a_vets", clinica=self.clinica_a)
        self.admin_a.groups.add(admin_group)

        # Clínica B con su admin
        self.clinica_b = make_clinica("Clínica B Vets")
        self.admin_b = make_user(username="admin_b_vets", clinica=self.clinica_b)
        self.admin_b.groups.add(admin_group)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _crear_veterinario_en_clinica(self, clinica, suffix=""):
        """Crea un veterinario directamente en la clínica dada."""
        from django.contrib.auth.models import User
        from clinic.models import PerfilUsuario
        vet_user = User.objects.create_user(
            username=f"vet_{clinica.id}_{suffix}",
            email=f"vet_{clinica.id}_{suffix}@test.cl",
            password="testpass123",
            first_name=f"Vet {suffix}",
        )
        PerfilUsuario.objects.create(
            user=vet_user,
            clinica=clinica,
            rol=PerfilUsuario.Rol.VETERINARIO,
        )
        return vet_user

    # ── GET /api/v1/veterinarios/ ─────────────────────────────────────────────

    def test_get_lista_solo_veterinarios_de_la_clinica(self):
        """GET devuelve únicamente los veterinarios de la clínica del admin autenticado."""
        vet_a = self._crear_veterinario_en_clinica(self.clinica_a, "get_a")
        self._crear_veterinario_en_clinica(self.clinica_b, "get_b")

        self._auth(self.admin_a)
        response = self.client.get("/api/v1/veterinarios/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        ids_devueltos = [v["id"] for v in data]
        self.assertIn(vet_a.id, ids_devueltos)
        # El veterinario de clínica B no debe aparecer
        vet_b_ids = list(
            __import__("clinic.models", fromlist=["PerfilUsuario"])
            .PerfilUsuario.objects.filter(clinica=self.clinica_b)
            .values_list("user_id", flat=True)
        )
        for bid in vet_b_ids:
            self.assertNotIn(bid, ids_devueltos)

    def test_get_sin_perfil_devuelve_403(self):
        """GET con usuario sin PerfilUsuario devuelve HTTP 403 (no es admin)."""
        from django.contrib.auth.models import User
        user_sin_perfil = User.objects.create_user(
            username="admin_sin_perfil_get",
            email="admin_sin_perfil_get@test.cl",
            password="testpass123",
        )
        # Sin PerfilUsuario → es_admin() devuelve False → 403 "rol de administrador"
        self._auth(user_sin_perfil)
        response = self.client.get("/api/v1/veterinarios/")

        self.assertEqual(response.status_code, 403)
        self.assertIn("administrador", response.json().get("detail", ""))

    # ── POST /api/v1/veterinarios/ ────────────────────────────────────────────

    def test_post_crea_veterinario_en_clinica_del_admin(self):
        """POST crea un veterinario asociado a la clínica del admin autenticado."""
        from clinic.models import PerfilUsuario
        self._auth(self.admin_a)
        payload = {
            "nombre": "Nuevo Vet",
            "email": "nuevo_vet_post@test.cl",
            "password": "securepass123",
        }
        response = self.client.post("/api/v1/veterinarios/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["rol"], "veterinario")

        # Verificar que el PerfilUsuario creado pertenece a clinica_a
        perfil = PerfilUsuario.objects.get(user_id=data["id"])
        self.assertEqual(perfil.clinica, self.clinica_a)

    def test_post_sin_perfil_devuelve_403(self):
        """POST con usuario sin PerfilUsuario devuelve HTTP 403 (no es admin)."""
        from django.contrib.auth.models import User
        user_sin_perfil = User.objects.create_user(
            username="admin_sin_perfil_post",
            email="admin_sin_perfil_post@test.cl",
            password="testpass123",
        )
        # Sin PerfilUsuario → es_admin() devuelve False → 403 "rol de administrador"
        self._auth(user_sin_perfil)
        payload = {
            "nombre": "Vet Sin Clinica",
            "email": "vet_sin_clinica@test.cl",
            "password": "securepass123",
        }
        response = self.client.post("/api/v1/veterinarios/", payload, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertIn("administrador", response.json().get("detail", ""))

    # ── PATCH /api/v1/veterinarios/<pk>/ ─────────────────────────────────────

    def test_patch_edita_veterinario_de_la_misma_clinica(self):
        """PATCH edita un veterinario que pertenece a la misma clínica del admin."""
        vet = self._crear_veterinario_en_clinica(self.clinica_a, "patch_ok")

        self._auth(self.admin_a)
        response = self.client.patch(
            f"/api/v1/veterinarios/{vet.id}/",
            {"nombre": "Nombre Editado"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nombre"], "Nombre Editado")

    def test_patch_veterinario_de_otra_clinica_devuelve_404(self):
        """PATCH de un veterinario de otra clínica devuelve HTTP 404 (req. 5.4)."""
        vet_b = self._crear_veterinario_en_clinica(self.clinica_b, "patch_cross")

        self._auth(self.admin_a)
        response = self.client.patch(
            f"/api/v1/veterinarios/{vet_b.id}/",
            {"nombre": "Intento Cross"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_patch_sin_perfil_devuelve_403(self):
        """PATCH con usuario sin PerfilUsuario devuelve HTTP 403 (no es admin)."""
        from django.contrib.auth.models import User
        user_sin_perfil = User.objects.create_user(
            username="admin_sin_perfil_patch",
            email="admin_sin_perfil_patch@test.cl",
            password="testpass123",
        )
        vet = self._crear_veterinario_en_clinica(self.clinica_a, "patch_noperfil")

        # Sin PerfilUsuario → es_admin() devuelve False → 403 "rol de administrador"
        self._auth(user_sin_perfil)
        response = self.client.patch(
            f"/api/v1/veterinarios/{vet.id}/",
            {"nombre": "No Debería"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("administrador", response.json().get("detail", ""))

    # ── DELETE /api/v1/veterinarios/<pk>/ ────────────────────────────────────

    def test_delete_desactiva_veterinario_de_la_misma_clinica(self):
        """DELETE desactiva un veterinario que pertenece a la misma clínica del admin."""
        from django.contrib.auth.models import User
        vet = self._crear_veterinario_en_clinica(self.clinica_a, "delete_ok")

        self._auth(self.admin_a)
        response = self.client.delete(f"/api/v1/veterinarios/{vet.id}/")

        self.assertEqual(response.status_code, 204)
        vet_user = User.objects.get(pk=vet.id)
        self.assertFalse(vet_user.is_active)

    def test_delete_veterinario_de_otra_clinica_devuelve_404(self):
        """DELETE de un veterinario de otra clínica devuelve HTTP 404 (req. 5.4)."""
        vet_b = self._crear_veterinario_en_clinica(self.clinica_b, "delete_cross")

        self._auth(self.admin_a)
        response = self.client.delete(f"/api/v1/veterinarios/{vet_b.id}/")

        self.assertEqual(response.status_code, 404)

    def test_delete_sin_perfil_devuelve_403(self):
        """DELETE con usuario sin PerfilUsuario devuelve HTTP 403 (no es admin)."""
        from django.contrib.auth.models import User
        user_sin_perfil = User.objects.create_user(
            username="admin_sin_perfil_delete",
            email="admin_sin_perfil_delete@test.cl",
            password="testpass123",
        )
        vet = self._crear_veterinario_en_clinica(self.clinica_a, "delete_noperfil")

        # Sin PerfilUsuario → es_admin() devuelve False → 403 "rol de administrador"
        self._auth(user_sin_perfil)
        response = self.client.delete(f"/api/v1/veterinarios/{vet.id}/")

        self.assertEqual(response.status_code, 403)
        self.assertIn("administrador", response.json().get("detail", ""))


# ─── Fix 3: Tests de aislamiento de tenant para ViewSets con get_queryset ─────

class TenantAislamientoViewSetTest(TestCase):
    """
    Verifica que CitaViewSet, VacunaViewSet, TratamientoViewSet y
    ArchivoDocumentoViewSet aplican el filtro de tenant correctamente.

    Cada ViewSet sobreescribe get_queryset() — estos tests garantizan que
    el filtro de clínica no se omite accidentalmente en futuras refactorizaciones.
    """

    def setUp(self):
        from clinic.models import (
            Cita, Especie, FichaClinica, Paciente, PerfilUsuario,
            SexoPaciente, TipoArchivoDocumento, Tratamiento, Vacuna,
        )
        from django.utils import timezone
        from datetime import date

        self.client = APIClient()

        # Dos clínicas independientes
        self.clinica_a = make_clinica("Clínica Tenant A")
        self.clinica_b = make_clinica("Clínica Tenant B")

        # Un usuario por clínica
        self.user_a = make_user(username="tenant_user_a", clinica=self.clinica_a)
        self.user_b = make_user(username="tenant_user_b", clinica=self.clinica_b)

        # Datos de soporte para clínica A
        especie_a = Especie.objects.create(nombre="Perro Tenant A", clinica=self.clinica_a)
        sexo_a = SexoPaciente.objects.create(nombre="Macho Tenant A", clinica=self.clinica_a)
        tutor_a = Tutor.objects.create(nombre="Tutor Tenant A", telefono="111", clinica=self.clinica_a)
        self.paciente_a = Paciente.objects.create(
            nombre="Paciente A", tutor=tutor_a, especie=especie_a, sexo=sexo_a, clinica=self.clinica_a
        )

        # Datos de soporte para clínica B
        especie_b = Especie.objects.create(nombre="Gato Tenant B", clinica=self.clinica_b)
        sexo_b = SexoPaciente.objects.create(nombre="Hembra Tenant B", clinica=self.clinica_b)
        tutor_b = Tutor.objects.create(nombre="Tutor Tenant B", telefono="222", clinica=self.clinica_b)
        self.paciente_b = Paciente.objects.create(
            nombre="Paciente B", tutor=tutor_b, especie=especie_b, sexo=sexo_b, clinica=self.clinica_b
        )

        # Citas
        self.cita_a = Cita.objects.create(
            paciente=self.paciente_a, tutor=tutor_a, fecha_hora=timezone.now(),
            motivo="Consulta A", clinica=self.clinica_a,
        )
        self.cita_b = Cita.objects.create(
            paciente=self.paciente_b, tutor=tutor_b, fecha_hora=timezone.now(),
            motivo="Consulta B", clinica=self.clinica_b,
        )

        # Vacunas
        self.vacuna_a = Vacuna.objects.create(
            paciente=self.paciente_a, nombre_vacuna="Rabia A",
            fecha_aplicacion=date.today(), clinica=self.clinica_a,
        )
        self.vacuna_b = Vacuna.objects.create(
            paciente=self.paciente_b, nombre_vacuna="Rabia B",
            fecha_aplicacion=date.today(), clinica=self.clinica_b,
        )

        # Tratamientos
        self.tratamiento_a = Tratamiento.objects.create(
            paciente=self.paciente_a, medicamento="Med A", dosis="1mg",
            frecuencia="Diario", fecha_inicio=date.today(), clinica=self.clinica_a,
        )
        self.tratamiento_b = Tratamiento.objects.create(
            paciente=self.paciente_b, medicamento="Med B", dosis="2mg",
            frecuencia="Diario", fecha_inicio=date.today(), clinica=self.clinica_b,
        )

        # Archivos
        tipo_a = TipoArchivoDocumento.objects.create(nombre="Rx A", clinica=self.clinica_a)
        tipo_b = TipoArchivoDocumento.objects.create(nombre="Rx B", clinica=self.clinica_b)
        self.archivo_a = ArchivoDocumento.objects.create(
            paciente=self.paciente_a, tipo=tipo_a,
            archivo_url="https://example.com/a.pdf", clinica=self.clinica_a,
        )
        self.archivo_b = ArchivoDocumento.objects.create(
            paciente=self.paciente_b, tipo=tipo_b,
            archivo_url="https://example.com/b.pdf", clinica=self.clinica_b,
        )

    def _ids(self, response):
        data = response.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        return {item["id"] for item in items}

    # ── Citas ─────────────────────────────────────────────────────────────────

    def test_citas_solo_devuelve_de_clinica_propia(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/api/v1/citas/")
        self.assertEqual(response.status_code, 200)
        ids = self._ids(response)
        self.assertIn(self.cita_a.id, ids)
        self.assertNotIn(self.cita_b.id, ids)

    def test_citas_no_accede_a_cita_de_otra_clinica(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f"/api/v1/citas/{self.cita_b.id}/")
        self.assertEqual(response.status_code, 404)

    # ── Vacunas ───────────────────────────────────────────────────────────────

    def test_vacunas_solo_devuelve_de_clinica_propia(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/api/v1/vacunas/")
        self.assertEqual(response.status_code, 200)
        ids = self._ids(response)
        self.assertIn(self.vacuna_a.id, ids)
        self.assertNotIn(self.vacuna_b.id, ids)

    def test_vacunas_no_accede_a_vacuna_de_otra_clinica(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f"/api/v1/vacunas/{self.vacuna_b.id}/")
        self.assertEqual(response.status_code, 404)

    # ── Tratamientos ──────────────────────────────────────────────────────────

    def test_tratamientos_solo_devuelve_de_clinica_propia(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/api/v1/tratamientos/")
        self.assertEqual(response.status_code, 200)
        ids = self._ids(response)
        self.assertIn(self.tratamiento_a.id, ids)
        self.assertNotIn(self.tratamiento_b.id, ids)

    def test_tratamientos_no_accede_a_tratamiento_de_otra_clinica(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f"/api/v1/tratamientos/{self.tratamiento_b.id}/")
        self.assertEqual(response.status_code, 404)

    # ── Archivos ──────────────────────────────────────────────────────────────

    def test_archivos_solo_devuelve_de_clinica_propia(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/api/v1/archivos/")
        self.assertEqual(response.status_code, 200)
        ids = self._ids(response)
        self.assertIn(self.archivo_a.id, ids)
        self.assertNotIn(self.archivo_b.id, ids)

    def test_archivos_no_accede_a_archivo_de_otra_clinica(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f"/api/v1/archivos/{self.archivo_b.id}/")
        self.assertEqual(response.status_code, 404)
