from django.db import migrations, models


def migrar_corte3(apps, schema_editor):
    """Cortes antiguos con numero_corte=3 pasan a numero_corte=1, adicional_letra='A'."""
    Corte = apps.get_model("cortes", "Corte")
    Corte.objects.filter(numero_corte=3).update(numero_corte=1, adicional_letra="A")


class Migration(migrations.Migration):
    dependencies = [
        ("cortes", "0004_presenciacorte"),
    ]

    operations = [
        migrations.AddField(
            model_name="corte",
            name="adicional_letra",
            field=models.CharField(blank=True, default="", max_length=1),
        ),
        migrations.RunPython(migrar_corte3, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name="corte",
            name="numero_corte",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "Corte 1"), (2, "Corte 2")]
            ),
        ),
        migrations.AddConstraint(
            model_name="corte",
            constraint=models.UniqueConstraint(
                fields=["fecha", "numero_corte", "adicional_letra"],
                name="uq_corte_fecha_numero_letra",
            ),
        ),
    ]
