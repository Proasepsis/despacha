from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="CredencialVigia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100, unique=True)),
                ("identificador", models.CharField(editable=False, max_length=16, unique=True)),
                ("token_sha256", models.CharField(editable=False, max_length=64)),
                ("ips_permitidas", models.JSONField(blank=True, default=list)),
                ("activo", models.BooleanField(default=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("ultimo_uso_en", models.DateTimeField(blank=True, null=True)),
                ("ultima_ip", models.GenericIPAddressField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Credencial de API Vigia",
                "verbose_name_plural": "Credenciales de API Vigia",
                "ordering": ["nombre"],
            },
        ),
    ]
