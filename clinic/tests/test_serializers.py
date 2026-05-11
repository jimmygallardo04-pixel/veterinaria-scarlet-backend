"""
Tests unitarios de serializers.

Verifican validaciones de campo y validaciones cruzadas sin HTTP.
"""

from datetime import date, timedelta

from django.test import TestCase

from clinic.serializers import (
    EspecieSerializer,
    PacienteSerializer,
    TratamientoSerializer,
    TutorSerializer,
    VacunaSerializer,
    FichaClinicaSerializer,
)
from .helpers import make_clinica, make_especie, make_paciente, make_sexo, make_tutor


# ─── PacienteSerializer ───────────────────────────────────────────────────────

class PacienteSerializerTest(TestCase):

    def setUp(self):
        self.tutor = make_tutor()
        self.especie = make_especie()
        self.sexo = make_sexo()

    def _data(self, **kwargs):
        defaults = dict(
            tutor=self.tutor.pk,
            nombre="Firulais",
            especie=self.especie.pk,
            sexo=self.sexo.pk,
        )
        defaults.update(kwargs)
        return defaults

    def test_fecha_nacimiento_futura_invalida(self):
        data = self._data(fecha_nacimiento=date.today() + timedelta(days=1))
        s = PacienteSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("fecha_nacimiento", s.errors)

    def test_fecha_nacimiento_hoy_valida(self):
        data = self._data(fecha_nacimiento=date.today())
        s = PacienteSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)

    def test_fecha_nacimiento_pasada_valida(self):
        data = self._data(fecha_nacimiento=date.today() - timedelta(days=365))
        s = PacienteSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)

    def test_fecha_nacimiento_none_valida(self):
        data = self._data(fecha_nacimiento=None)
        s = PacienteSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)


# ─── VacunaSerializer ─────────────────────────────────────────────────────────

class VacunaSerializerTest(TestCase):

    def setUp(self):
        tutor = make_tutor()
        self.paciente = make_paciente(tutor)
        self.hoy = date.today()

    def _data(self, **kwargs):
        defaults = dict(
            paciente=self.paciente.pk,
            nombre_vacuna="Rabia",
            fecha_aplicacion=self.hoy - timedelta(days=1),
            proxima_dosis=self.hoy + timedelta(days=30),
        )
        defaults.update(kwargs)
        return defaults

    def test_proxima_dosis_posterior_valida(self):
        s = VacunaSerializer(data=self._data())
        self.assertTrue(s.is_valid(), s.errors)

    def test_proxima_dosis_igual_invalida(self):
        s = VacunaSerializer(data=self._data(
            fecha_aplicacion=self.hoy,
            proxima_dosis=self.hoy,
        ))
        self.assertFalse(s.is_valid())
        self.assertIn("proxima_dosis", s.errors)

    def test_proxima_dosis_anterior_invalida(self):
        s = VacunaSerializer(data=self._data(
            fecha_aplicacion=self.hoy,
            proxima_dosis=self.hoy - timedelta(days=1),
        ))
        self.assertFalse(s.is_valid())
        self.assertIn("proxima_dosis", s.errors)

    def test_sin_proxima_dosis_valida(self):
        s = VacunaSerializer(data=self._data(proxima_dosis=None))
        self.assertTrue(s.is_valid(), s.errors)


# ─── TratamientoSerializer ────────────────────────────────────────────────────

class TratamientoSerializerTest(TestCase):

    def setUp(self):
        tutor = make_tutor()
        self.paciente = make_paciente(tutor)
        self.hoy = date.today()

    def _data(self, **kwargs):
        defaults = dict(
            paciente=self.paciente.pk,
            medicamento="Amoxicilina",
            dosis="250mg",
            frecuencia="Cada 8h",
            fecha_inicio=self.hoy,
            fecha_fin=self.hoy + timedelta(days=7),
        )
        defaults.update(kwargs)
        return defaults

    def test_fecha_fin_posterior_valida(self):
        s = TratamientoSerializer(data=self._data())
        self.assertTrue(s.is_valid(), s.errors)

    def test_fecha_fin_igual_valida(self):
        s = TratamientoSerializer(data=self._data(fecha_fin=self.hoy))
        self.assertTrue(s.is_valid(), s.errors)

    def test_fecha_fin_anterior_invalida(self):
        s = TratamientoSerializer(data=self._data(
            fecha_inicio=self.hoy,
            fecha_fin=self.hoy - timedelta(days=1),
        ))
        self.assertFalse(s.is_valid())
        self.assertIn("fecha_fin", s.errors)

    def test_sin_fecha_fin_valida(self):
        s = TratamientoSerializer(data=self._data(fecha_fin=None))
        self.assertTrue(s.is_valid(), s.errors)


# ─── FichaClinicaSerializer ───────────────────────────────────────────────────

class FichaClinicaSerializerTest(TestCase):

    def setUp(self):
        tutor = make_tutor()
        self.paciente = make_paciente(tutor)

    def _data(self, **kwargs):
        defaults = dict(
            paciente=self.paciente.pk,
            motivo_consulta="Revisión general",
        )
        defaults.update(kwargs)
        return defaults

    def test_peso_negativo_invalido(self):
        s = FichaClinicaSerializer(data=self._data(peso_kg=-1))
        self.assertFalse(s.is_valid())
        self.assertIn("peso_kg", s.errors)

    def test_peso_cero_invalido(self):
        s = FichaClinicaSerializer(data=self._data(peso_kg=0))
        self.assertFalse(s.is_valid())
        self.assertIn("peso_kg", s.errors)

    def test_peso_valido(self):
        s = FichaClinicaSerializer(data=self._data(peso_kg="4.50"))
        self.assertTrue(s.is_valid(), s.errors)

    def test_temperatura_fuera_de_rango_invalida(self):
        s = FichaClinicaSerializer(data=self._data(temperatura="50.0"))
        self.assertFalse(s.is_valid())
        self.assertIn("temperatura", s.errors)

    def test_temperatura_valida(self):
        s = FichaClinicaSerializer(data=self._data(temperatura="38.5"))
        self.assertTrue(s.is_valid(), s.errors)

    def test_frecuencia_cardiaca_fuera_de_rango_invalida(self):
        s = FichaClinicaSerializer(data=self._data(frecuencia_cardiaca=600))
        self.assertFalse(s.is_valid())
        self.assertIn("frecuencia_cardiaca", s.errors)

    def test_frecuencia_respiratoria_fuera_de_rango_invalida(self):
        s = FichaClinicaSerializer(data=self._data(frecuencia_respiratoria=300))
        self.assertFalse(s.is_valid())
        self.assertIn("frecuencia_respiratoria", s.errors)

    def test_ficha_minima_valida(self):
        s = FichaClinicaSerializer(data=self._data())
        self.assertTrue(s.is_valid(), s.errors)


# ─── Clinica read-only en serializers ────────────────────────────────────────

class SerializerClinicaReadOnlyTest(TestCase):
    """
    Verifica que el campo `clinica` es read-only en los serializers de dominio.

    Valida: Requisitos 10.2, 10.3, 6.4, 6.5
    """

    def setUp(self):
        self.clinica_a = make_clinica("Clínica A")
        self.clinica_b = make_clinica("Clínica B")

    def test_tutor_serializer_ignora_clinica_en_input(self):
        """
        Enviar clinica=999 en el body de TutorSerializer no modifica el campo.
        El campo es read_only, por lo que no aparece en validated_data.
        """
        data = {
            "nombre": "Juan Pérez",
            "telefono": "987654321",
            "clinica": 999,  # ID inexistente — debe ser ignorado
        }
        s = TutorSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        # clinica no debe estar en validated_data porque es read_only
        self.assertNotIn("clinica", s.validated_data)

    def test_tutor_serializer_ignora_clinica_valida_en_input(self):
        """
        Enviar clinica=clinica_b.id tampoco modifica el campo aunque sea válido.
        """
        tutor = make_tutor(clinica=self.clinica_a)
        data = {
            "nombre": tutor.nombre,
            "telefono": tutor.telefono,
            "clinica": self.clinica_b.id,  # clínica válida pero debe ignorarse
        }
        s = TutorSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        self.assertNotIn("clinica", s.validated_data)

    def test_especie_serializer_acepta_mismo_nombre_en_dos_clinicas(self):
        """
        EspecieSerializer acepta el mismo nombre para dos clínicas distintas
        (sin error de unicidad), porque unique_together es (nombre, clinica).
        """
        nombre = "Reptil"

        # Crear especie en clínica A
        especie_a = make_especie(nombre=nombre, clinica=self.clinica_a)

        # Serializar datos para clínica B con el mismo nombre
        # El serializer no valida unicidad de clinica (es read_only),
        # así que is_valid() debe pasar sin errores de unicidad.
        data = {"nombre": nombre}
        s = EspecieSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)

    def test_especie_serializer_clinica_no_en_validated_data(self):
        """
        El campo clinica no aparece en validated_data de EspecieSerializer.
        """
        data = {"nombre": "Ave", "clinica": self.clinica_a.id}
        s = EspecieSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)
        self.assertNotIn("clinica", s.validated_data)
