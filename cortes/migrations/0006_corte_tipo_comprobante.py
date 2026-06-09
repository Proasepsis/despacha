from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cortes", "0005_corte_adicional_letra"),
    ]

    operations = [
        migrations.AddField(
            model_name="corte",
            name="tipo_comprobante",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
    ]
