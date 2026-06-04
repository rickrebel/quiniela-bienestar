"""Crea los StageUser faltantes para cada par (usuario, fase).

Idempotente: solo inserta los que no existen. Útil tras agregar una
fase nueva o para respaldar a usuarios creados antes del backfill.
"""

from django.core.management.base import BaseCommand

from pool.models import StageUser, User
from tournament.models import Stage


class Command(BaseCommand):
    help = "Asegura un StageUser por cada (usuario, fase)."

    def handle(self, *args, **options) -> None:
        stages = list(Stage.objects.all())
        existing = set(
            StageUser.objects.values_list("user_id", "stage_id")
        )
        to_create = [
            StageUser(user=user, stage=stage)
            for user in User.objects.all()
            for stage in stages
            if (user.id, stage.id) not in existing
        ]
        StageUser.objects.bulk_create(to_create)

        self.stdout.write(self.style.SUCCESS(
            f"StageUser creados: {len(to_create)}."
        ))
