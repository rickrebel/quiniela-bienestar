"""Crea las 8 fases atómicas del torneo (idempotente).

Los grupos se parten en 3 sub-fases (una por jornada, ``is_group=True``,
orders 1-3); las 5 eliminatorias toman orders 4-8. THIRD_PLACE y FINAL de
FD se colapsan aquí en la fase FINAL (chip "finales"). Los colores son
tentativos; ajústalos a gusto.
"""

from django.core.management.base import BaseCommand

from tournament.models import Stage
from tournament.services.group_rounds import (
    SUBGROUP_COLOR, SUBGROUP_STAGES)

# Eliminatorias: (key, name, short_name, color, order). Orders 4-8 dejan
# 1-3 para las 3 sub-fases de grupos.
KNOCKOUTS = [
    (Stage.LAST_32, "Dieciseisavos de final", "16avos", "#2196F3", 4),
    (Stage.LAST_16, "Octavos de final", "octavos", "#00BCD4", 5),
    (Stage.QUARTER_FINALS, "Cuartos de final", "cuartos", "#FF9800", 6),
    (Stage.SEMI_FINALS, "Semifinales", "semis", "#9C27B0", 7),
    (Stage.FINAL, "Finales", "finales", "#F44336", 8),
]


class Command(BaseCommand):
    help = "Crea o actualiza las 8 fases atómicas del torneo."

    def handle(self, *args, **options) -> None:
        for key, name, short_name, order in SUBGROUP_STAGES:
            Stage.objects.update_or_create(
                key=key,
                defaults={
                    "name": name,
                    "short_name": short_name,
                    "color": SUBGROUP_COLOR,
                    "order": order,
                    "is_group": True,
                },
            )
        for key, name, short_name, color, order in KNOCKOUTS:
            Stage.objects.update_or_create(
                key=key,
                defaults={
                    "name": name,
                    "short_name": short_name,
                    "color": color,
                    "order": order,
                    "is_group": False,
                },
            )

        total = len(SUBGROUP_STAGES) + len(KNOCKOUTS)
        self.stdout.write(self.style.SUCCESS(f"Fases cargadas: {total}."))
