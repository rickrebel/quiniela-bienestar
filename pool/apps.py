from django.apps import AppConfig


class PoolConfig(AppConfig):
    """Configuración de la app de la quiniela (usuarios y pronósticos)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "pool"
    verbose_name = "Quiniela"
