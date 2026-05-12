"""
Migración 0018:
  1. Cambia el default de ArchivoDocumento.fecha de timezone.now a date.today
     para evitar que la fecha UTC difiera de la fecha local (America/Santiago).
  2. Agrega índice compuesto (email, usado, creado_en) en CodigoVerificacion
     para optimizar la query de email_esta_verificado().
"""

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0017_add_index_codigo_expira_en"),
    ]

    operations = [
        # Cambiar default de ArchivoDocumento.fecha a date.today
        migrations.AlterField(
            model_name="archivodocumento",
            name="fecha",
            field=models.DateField(
                db_index=True,
                default=datetime.date.today,
            ),
        ),
        # Agregar índice compuesto para email_esta_verificado
        migrations.AddIndex(
            model_name="codigoverificacion",
            index=models.Index(
                fields=["email", "usado", "creado_en"],
                name="idx_codigo_verificado",
            ),
        ),
    ]
