from django.apps import AppConfig


class CortesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cortes"

    def ready(self):
        import cortes.signals  # noqa: F401
