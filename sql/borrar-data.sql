-- Limpia todos los datos de la aplicación y reinicia las secuencias de IDs.
-- Útil para resetear el entorno de desarrollo sin borrar el esquema.
--
-- ADVERTENCIA: Esto borra TODOS los datos. No ejecutar en producción.
-- Uso: psql $DATABASE_URL -f sql/borrar-data.sql

TRUNCATE TABLE
  clinic_archivodocumento,
  clinic_cita,
  clinic_codigoverificacion,
  clinic_especie,
  clinic_fichaclinica,
  clinic_paciente,
  clinic_perfilusuario,
  clinic_sexopaciente,
  clinic_tipoarchivodocumento,
  clinic_tratamiento,
  clinic_tutor,
  clinic_vacuna,
  clinic_clinica,
  django_admin_log,
  django_session,
  auth_user
RESTART IDENTITY CASCADE;
