from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0016_add_index_codigo_email_creado"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="codigoverificacion",
            index=models.Index(fields=["expira_en"], name="idx_codigo_expira_en"),
        ),
    ]
