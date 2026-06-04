"""Auto-confirma las fases enviadas cuyo plazo de confirmación venció.

Por cada StageUser con ``sent_at`` pero sin ``closed_at`` y cuya fase ya
pasó su ``confirm_deadline``: marca ``closed_at`` y manda el Excel final.

PENDIENTE: programar como cron en EC2 (ver docs/design-models/decisiones.md).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from pool.models import StageUser
from pool.services.excel import generate_excel


class Command(BaseCommand):
    help = "Cierra (confirma) las fases enviadas cuyo plazo ya venció."

    def handle(self, *args, **options) -> None:
        now = timezone.now()
        pending = StageUser.objects.select_related("stage", "user").filter(
            sent_at__isnull=False,
            closed_at__isnull=True,
            stage__confirm_deadline__isnull=False,
            stage__confirm_deadline__lte=now,
        )

        count = 0
        for stage_user in pending:
            stage_user.closed_at = now
            stage_user.save(update_fields=["closed_at"])
            generate_excel(stage_user.user, stage_user.stage)
            count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Fases auto-confirmadas: {count}."
        ))
