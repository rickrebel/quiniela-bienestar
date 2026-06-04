from django.apps import AppConfig


class TournamentConfig(AppConfig):
    """Configuración de la app de datos deportivos del torneo."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tournament"
    verbose_name = "Torneo"
