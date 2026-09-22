from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cortes", "0010_linea_punto_incluido"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="corte",
            index=models.Index(
                fields=["estado", "actualizado_en"],
                name="corte_estado_actualizado_idx",
            ),
        ),
    ]
