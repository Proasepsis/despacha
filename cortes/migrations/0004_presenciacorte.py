import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cortes", "0003_documento_novedad"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PresenciaCorte",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("visto_en", models.DateTimeField()),
                ("corte", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="presencias", to="cortes.corte")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="presencias_corte", to=settings.AUTH_USER_MODEL)),
            ],
            options={"unique_together": {("user", "corte")}},
        ),
    ]
