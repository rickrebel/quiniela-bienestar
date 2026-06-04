"""Crea las 6 fases del torneo (idempotente).

Los colores son tentativos; ajústalos a gusto. THIRD_PLACE y FINAL de
FD se colapsan aquí en la fase FINAL (chip "finales").
"""

from django.core.management.base import BaseCommand

from tournament.models import Stage

# (key, name, short_name, color, order)
STAGES = [
    (Stage.GROUP_STAGE, "Fase de grupos", "grupos", "#4CAF50", 1),
    (Stage.LAST_32, "Dieciseisavos de final", "16avos", "#2196F3", 2),
    (Stage.LAST_16, "Octavos de final", "octavos", "#00BCD4", 3),
    (Stage.QUARTER_FINALS, "Cuartos de final", "cuartos", "#FF9800", 4),
    (Stage.SEMI_FINALS, "Semifinales", "semis", "#9C27B0", 5),
    (Stage.FINAL, "Finales", "finales", "#F44336", 6),
]


class Command(BaseCommand):
    help = "Crea o actualiza las 6 fases del torneo."

    def handle(self, *args, **options) -> None:
        for key, name, short_name, color, order in STAGES:
            Stage.objects.update_or_create(
                key=key,
                defaults={
                    "name": name,
                    "short_name": short_name,
                    "color": color,
                    "order": order,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"Fases cargadas: {len(STAGES)}."
        ))
