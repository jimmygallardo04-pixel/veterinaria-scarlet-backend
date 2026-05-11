# Generated migration: alter clinica FK from nullable to NOT NULL on all domain models.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0011_data_migration_tenant"),
    ]

    operations = [
        migrations.AlterField(
            model_name="archivodocumento",
            name="clinica",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="clinic.clinica",
            ),
        ),
        migrations.AlterField(
            model_name="cita",
            name="clinica",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="clinic.clinica",
            ),
        ),
        migrations.AlterField(
            model_name="especie",
            name="clinica",
            field=models.ForeignKey(
                db_index=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="clinic.clinica",
            ),
        ),
        migrations.AlterField(
            model_name="fichaclinica",
            name="clinica",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="clinic.clinica",
            ),
        ),
        migrations.AlterField(
            model_name="paciente",
            name="clinica",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="clinic.clinica",
            ),
        ),
        migrations.AlterField(
            model_name="sexopaciente",
            name="clinica",
            field=models.ForeignKey(
                db_index=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="clinic.clinica",
            ),
        ),
        migrations.AlterField(
            model_name="tipoarchivodocumento",
            name="clinica",
            field=models.ForeignKey(
                db_index=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="clinic.clinica",
            ),
        ),
        migrations.AlterField(
            model_name="tratamiento",
            name="clinica",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="clinic.clinica",
            ),
        ),
        migrations.AlterField(
            model_name="tutor",
            name="clinica",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="clinic.clinica",
            ),
        ),
        migrations.AlterField(
            model_name="vacuna",
            name="clinica",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="clinic.clinica",
            ),
        ),
    ]
