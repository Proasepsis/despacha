import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="IngestionSiigo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("extraction_id", models.UUIDField(unique=True)),
                ("schema_version", models.CharField(max_length=20)),
                ("source", models.CharField(max_length=50)),
                ("window_start", models.DateField()),
                ("window_end", models.DateField()),
                ("generated_at", models.DateTimeField()),
                ("raw_sha256", models.CharField(max_length=64)),
                ("raw_size_bytes", models.PositiveBigIntegerField()),
                ("content_sha256", models.CharField(max_length=64)),
                ("rows_sha256", models.CharField(db_index=True, max_length=64)),
                ("row_count", models.PositiveIntegerField()),
                ("payload", models.JSONField()),
                ("source_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("estado", models.CharField(choices=[("recibido", "Recibido")], default="recibido", max_length=20)),
                ("recibido_en", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Ingestión SIIGO",
                "verbose_name_plural": "Ingestiones SIIGO",
                "ordering": ["-recibido_en"],
            },
        ),
    ]
