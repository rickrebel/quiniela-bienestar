from django.apps import AppConfig


class PoolConfig(AppConfig):
    """Configuración de la app de la quiniela (usuarios y pronósticos)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "pool"
    verbose_name = "Quiniela"

    def ready(self) -> None:
        """Registra las señales (alta de WindowUser vía UserQuiniela)."""
        from . import signals  # noqa: F401
